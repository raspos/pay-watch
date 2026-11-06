"""공개 JSON 내보내기. 허용 목록(allowlist) 방식: 여기 적힌 필드만 나간다(사업자번호·우편번호·상세주소 등은 나가지 않음).
계산 불가 값은 null 로 두며 0 으로 채우지 않는다."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import METHODOLOGY_VERSION
from .load_nps import normalize_alias, normalize_name

N_SHARDS = 1024
TOP_MIN_SUBS = 100
BADGE_KO = {"cap_caution": "급여 상한 주의", "pay_high_in_industry": "업종 내 고연봉", "headcount_up": "가입자 증가",
            "headcount_down": "가입자 감소", "loss_rate_high": "상실률 높음", "restructure_check": "사업장 변동 확인 필요"}

# 공개 상세 JSON 에 허용되는 키(테스트가 이 집합과 비교한다)
DETAIL_KEYS = {"id", "n", "t", "ind", "i2", "loc", "ym", "pp", "s", "a", "l", "e", "c", "m", "peer", "b", "grade", "fl", "ps"}
METRIC_KEYS = {"g12", "g3", "net12", "mom", "lr", "lc12", "ac12", "pc12", "pcr", "pct", "prem", "cen", "rs", "hc", "up"}


def search_key(name: str) -> str:
    return normalize_alias(normalize_name(name))


def shard_of(wp_id: int) -> int:
    return int(wp_id) % N_SHARDS


def chunk_name(sk: str) -> str:
    return "_".join(f"{ord(ch):x}" for ch in sk[:2]) if sk else "0"


def _num(x, nd=None):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) or (x is pd.NA):
        return None
    v = float(x)
    if math.isnan(v):
        return None
    return round(v, nd) if nd is not None else int(round(v))


def _s(v):
    """문자열 필드의 NaN/NA 를 None 으로(JSON 에 NaN 이 들어가면 브라우저 JSON.parse 가 실패한다)."""
    if v is None or v is pd.NA or (isinstance(v, float) and v != v):
        return None
    return v


def _id(r) -> int:
    return int(r["_id"]) if "_id" in r else int(r.name)


def _arr(row, nd=None, scale=1.0):
    return [_num(v * scale if v == v else v, nd) for v in row]


def build_detail(r: pd.Series, panel_rows: dict, months: list[str]) -> dict:
    """r: 최신월 지표 행, panel_rows: {'subs','acq','lost','est','cap'} 각 길이 13 배열."""
    pp = bool(r["pay_public"])
    est = None
    cap = None
    if pp:
        est = [(_num(v * 12 / 1000) * 1000 if v == v else None) for v in panel_rows["est"]]   # 천원 단위로 반올림한 연환산(원)
        # 가입자 10명 미만이던 달의 추정치는 공개 기준에 맞지 않아 비운다
        est = [e if (s == s and s >= 10) else None for e, s in zip(est, panel_rows["subs"])]
        cap = _arr(panel_rows["cap"], 3)
    m = {
        "g12": _num(r.get("growth_12m"), 4), "g3": _num(r.get("growth_3m"), 4), "net12": _num(r.get("net_12m")),
        "mom": _num(r.get("mom_change"), 4), "lr": _num(r.get("lost_rate_month"), 4), "lc12": _num(r.get("lost_cum_12m"), 4),
        "ac12": _num(r.get("acq_cum_12m"), 4), "up": _num(r.get("persist_up_12m")),
        "rs": bool(r.get("restructure_suspect")), "hc": bool(r.get("history_complete")),
    }
    if pp:
        m.update(pc12=_num(r.get("pay_change_12m"), 4), pcr=_s(r.get("pay_change_reason")), pct=_num(r.get("pay_pct"), 4),
                 prem=_num(r.get("pay_premium"), 4), cen=bool(r.get("pay_censored")))
    peer = None
    if pp and pd.notna(r.get("peer_n")):
        peer = {"n": _num(r["peer_n"]), "med": _num(r["peer_median"]), "p25": _num(r["peer_p25"]), "p75": _num(r["peer_p75"]),
                "scope": _s(r["peer_scope"]), "lvl": _num(r.get("peer_level")), "lab": _s(r.get("peer_label")), "size": str(r["size_bucket"])}
    return {
        "id": _id(r), "ps": bool(r.get("project_site")), "n": _s(r["name_raw"]), "t": "개인" if r["type_code"] == "2" else "법인", "ind": _s(r["industry_name"]),
        "i2": _s(r["ind2"]), "loc": _s(r["addr_jibun"]), "ym": months[-1], "pp": pp,
        "s": _arr(panel_rows["subs"]), "a": _arr(panel_rows["acq"]), "l": _arr(panel_rows["lost"]),
        "e": est, "c": cap, "m": m, "peer": peer,
        "b": [b for b in (_s(r.get("badges")) or "").split(",") if b] if pp else [],
        "grade": _s(r["grade"]) if pp else None,
        "fl": [f for f in (_s(r.get("flags")) or "").split("|") if f and f != "below_public_threshold"],
    }


def index_row(r: pd.Series) -> list:
    """검색 인덱스 한 줄: [id, 사업장명, 업종명, 소재지, 가입자 수, 연봉추정공개(1/0), 법인/개인]"""
    return [_id(r), _s(r["name_raw"]), _s(r["industry_name"]), _s(r["addr_jibun"]), int(r["subs"]), int(bool(r["pay_public"])), 1 if r["type_code"] == "2" else 0]


def scrub(o):
    """공개 JSON 직전 정리: NaN/inf 는 None, numpy 스칼라는 파이썬 값으로(재귀). NaN 이 남으면 write_json 이 실패한다."""
    if isinstance(o, dict):
        return {k: scrub(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [scrub(v) for v in o]
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")  # NaN 이 섞이면 즉시 실패


RANGE_SIZE = 1200      # 청크당 레코드 수(정렬된 검색 키 기준 연속 구간)
MAX_RANGE_FILES = 6    # 한 번의 검색에서 받는 청크 상한


def _u16(k: str) -> bytes:
    return k.encode("utf-16-be")   # JS 문자열 비교(UTF-16 코드 단위)와 같은 정렬 순서


def range_partition(recs: list, size: int = RANGE_SIZE):
    """recs: [(sk, row)] → (chunks, starts). 같은 sk 는 한 청크에 두어 경계에서 갈라지지 않게 한다."""
    recs = sorted(recs, key=lambda t: (_u16(t[0]), t[1][0]))
    chunks, starts, cur = [], [], []
    i = 0
    while i < len(recs):
        j = i
        while j < len(recs) and recs[j][0] == recs[i][0]:
            j += 1
        grp = recs[i:j]
        if cur and len(cur) + len(grp) > size:
            chunks.append(cur)
            cur = []
        if not cur:
            starts.append(grp[0][0])
        cur.extend(grp)
        i = j
    if cur:
        chunks.append(cur)
    return chunks, starts


def chunks_for_prefix(starts: list, q: str, cap: int = MAX_RANGE_FILES) -> list:
    """JS search.js 의 청크 선택과 동일. q 로 시작하는 키가 있을 수 있는 청크 번호들."""
    if not starts or not q:
        return []
    lo, hi = 0, len(starts) - 1
    while lo < hi:                                   # starts[i] <= q 인 마지막 i
        mid = (lo + hi + 1) // 2
        if _u16(starts[mid]) <= _u16(q):
            lo = mid
        else:
            hi = mid - 1
    out = [lo]
    j = lo + 1
    while j < len(starts) and starts[j].startswith(q) and len(out) < cap:
        out.append(j)
        j += 1
    return out


def export_indexes(d: pd.DataFrame, out: Path) -> dict:
    """d: search_visible 사업장(인덱스 wp_id). top.json(100명 이상) + 정렬 키 범위 청크(index/r/N.json, index/ranges.json)."""
    recs = d.assign(_id=d.index).to_dict("records")
    rows = {r["_id"]: index_row(r) for r in recs}
    top_ids = {r["_id"] for r in recs if r["subs"] >= TOP_MIN_SUBS}
    write_json(out / "index/top.json", [rows[i] for i in sorted(top_ids)])
    rest = [(search_key(r["name_raw"]), rows[r["_id"]]) for r in recs if r["_id"] not in top_ids]
    chunks, starts = range_partition(rest)
    for n, c in enumerate(chunks):
        write_json(out / f"index/r/{n}.json", [row for _, row in c])
    write_json(out / "index/ranges.json", starts)
    return {"top": len(top_ids), "chunks": len(chunks), "rest": len(rest)}


def rankings(d: pd.DataFrame, n=30) -> dict:
    """홈 카테고리용 목록. 설명 가능한 조건만 사용하며 '종합 순위'는 만들지 않는다."""
    ok = d[d["pay_public"] & d["grade"].isin(["B", "C"]) & ~d["restructure_suspect"].fillna(False) & ~d["project_site"].fillna(False)]
    def pack(df, keycol, note):
        return {"note": note, "items": [{"id": int(i), "n": _s(r["name_raw"]), "ind": _s(r["industry_name"]), "loc": _s(r["addr_jibun"]),
                                         "subs": int(r["subs"]), "v": _num(r[keycol], 4), "cap": bool(r["cap_flag"]),
                                         "est": _num(r["est_annual"])} for i, r in df.head(n).iterrows()]}

    tasty = ok[(ok["subs"] >= 30)].sort_values("est_annual", ascending=False)
    hidden = ok[(ok["subs"].between(30, 299)) & ~ok["cap_flag"].fillna(False) & ok["pay_premium"].notna() & ~ok["pay_censored"].fillna(False)]
    hidden = hidden.sort_values("pay_premium", ascending=False)
    raise_ = ok[(ok["subs"] >= 30) & ok["pay_change_12m"].notna()].sort_values("pay_change_12m", ascending=False)
    grow = ok[(ok["subs"] >= 50) & (ok["history_complete"]) & ok["growth_12m"].notna() & ((ok["subs"] - ok["net_12m"]) >= 30)].sort_values("growth_12m", ascending=False)
    return {
        "tasty": pack(tasty, "est_annual", "가입자 30명 이상, 국민연금 기준소득월액 연환산 추정금액 상위. 상한(월 659만원) 때문에 상위 기업의 값은 모두 하한값이라 순위 차이는 의미가 작음"),
        "hidden": pack(hidden, "pay_premium", "가입자 30~299명 중 같은 업종·규모 중앙값 대비 추정급여가 높은 사업장(상한 접근 기업 제외). '숨은'은 규모 기반 분류이며 인지도 자료가 아님"),
        "raise": pack(raise_, "pay_change_12m", "12개월 추정급여 변화율 상위(상한 접근 기업 제외). 직원 구성 변화 영향이 있어 임금 인상률이 아님"),
        "grow": pack(grow, "growth_12m", "12개월 국민연금 가입자 증가율 상위(가입자 50명 이상, 급변 의심 제외). 사업장 이전·합병 가능성은 확인되지 않음"),
    }


def meta(months, counts, rates=None, caps=None) -> dict:
    return {"rates": rates or [], "caps": caps or [], "base_month": months[-1], "months": months, "methodology_version": METHODOLOGY_VERSION, "counts": counts,
            "disclaimer": "국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다.",
            "cap_warning": "국민연금 기준소득월액 상한의 영향으로 실제 평균급여가 추정치보다 높을 수 있습니다.",
            "source": "국민연금공단_국민연금 가입 사업장 내역 (공공데이터포털 15083277)", "n_shards": N_SHARDS}
