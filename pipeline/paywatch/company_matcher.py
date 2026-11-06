"""NPS 사업장 ↔ DART 법인 매칭. 사업자번호 앞 6자리는 약한 식별자이므로 단독·이름과의 2중 일치만으로 확정하지 않는다.

등급
  verified         : 사람이 확정한 override(config/match_overrides.csv) 에 있는 경우만
  high_confidence  : 정규화명 일치 + 사업자번호6 일치 + 시도·시군구 일치 + 양쪽에서 후보가 유일(1:1)
  candidate        : 정규화명 + 사업자번호6 일치하나 주소 불일치/불명, 또는 후보 유일
  ambiguous        : 같은 근거로 DART 후보가 둘 이상(또는 한 법인에 같은 조건 사업장이 여럿이어도 주소가 다름은 허용하되 합산 안 함)
  unmatched        : 근거 없음 / 이름은 같지만 사업자번호6 불일치 / DART 개황 미수집
급여 수치는 매칭에 사용하지 않는다(순환 검증 방지)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .dart_client import CACHE
from .load_nps import normalize_alias, normalize_name

GRADES = ["verified", "high_confidence", "candidate", "ambiguous", "unmatched"]
_SIDO = {"서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주", "대전": "대전", "울산": "울산",
         "세종": "세종", "경기": "경기", "강원": "강원", "충북": "충북", "충청북": "충북", "충남": "충남", "충청남": "충남",
         "전북": "전북", "전라북": "전북", "전남": "전남", "전라남": "전남", "경북": "경북", "경상북": "경북",
         "경남": "경남", "경상남": "경남", "제주": "제주"}


def addr_key(a: str | None) -> tuple[str, str] | None:
    """(시도, 시군구) 정규화. 해석 못 하면 None."""
    if not isinstance(a, str):
        return None
    t = a.split()
    if len(t) < 2:
        return None
    sido = next((v for k, v in _SIDO.items() if t[0].startswith(k)), None)
    if not sido:
        return None
    gu = re.sub(r"\s", "", t[1])
    return sido, gu


def load_company_cache() -> pd.DataFrame:
    rows = []
    for p in (CACHE / "company").glob("*.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("status") != "000":
            continue
        rows.append({"corp_code": p.stem.split("_")[0], "corp_name": j.get("corp_name"), "stock_code": j.get("stock_code") or "",
                     "corp_cls": j.get("corp_cls"), "bizr_no": (j.get("bizr_no") or "").replace("-", ""),
                     "jurir_no": j.get("jurir_no"), "adres": j.get("adres"), "induty_code": j.get("induty_code"),
                     "acc_mt": j.get("acc_mt")})
    return pd.DataFrame(rows)


def load_overrides(path=None) -> pd.DataFrame:
    """config/match_overrides.csv: 사람이 근거를 확인해 확정한 매핑(사업자번호6 + 정규화 사업장명 + DART 고유번호)."""
    from .tables import CONFIG_DIR
    p = path or CONFIG_DIR / "match_overrides.csv"
    if not Path(p).exists():
        return pd.DataFrame(columns=["brn6", "name_norm", "corp_code", "evidence"])
    return pd.read_csv(p, dtype=str).fillna("")


def match(nps: pd.DataFrame, dart: pd.DataFrame, overrides: pd.DataFrame | None = None) -> pd.DataFrame:
    """사업장(wp_id)마다 DART 법인 후보를 점수화해 한 행으로 반환. 급여는 사용하지 않는다.
    점수: 5 이름+사업자번호6+시군구 / 4 이름+사업자번호6 / 3 음역 이름+사업자번호6 / 2 이름만(번호6 불일치).
    같은 최고점에 서로 다른 법인이 둘 이상이면 ambiguous(합산 금지). 점수 2는 공장·지점이 다른 세무서 번호를 쓰는
    경우를 포함하므로 합산 대상이 아니라 '후보'로만 둔다."""
    d = dart.copy()
    d["nn"] = d["corp_name"].map(normalize_name)
    d["na"] = d["nn"].map(normalize_alias)
    d["bizr6"] = d["bizr_no"].str[:6]
    d["ak"] = d["adres"].map(addr_key)
    n = nps[["wp_id", "name_norm", "brn6", "addr_jibun"]].copy()
    n["na"] = n["name_norm"].map(normalize_alias)
    n["ak"] = n["addr_jibun"].map(addr_key)

    dd = d[["corp_code", "nn", "na", "bizr6", "ak"]].rename(columns={"ak": "ak_d"})
    ex = n.merge(dd, left_on="name_norm", right_on="nn", how="inner")
    ex["exact"] = True
    al = n.merge(dd, on="na", how="inner", suffixes=("", "_d"))
    al = al[al["name_norm"] != al["nn"]].copy()
    al["exact"] = False
    pairs = pd.concat([ex, al], ignore_index=True)
    pairs["brn"] = pairs["brn6"] == pairs["bizr6"]
    pairs["addr"] = pairs["brn"] & pairs["ak"].notna() & pairs["ak_d"].notna() & (pairs["ak"] == pairs["ak_d"])
    pairs["score"] = 0
    pairs.loc[pairs.exact & ~pairs.brn, "score"] = 2
    pairs.loc[~pairs.exact & pairs.brn, "score"] = 3
    pairs.loc[pairs.exact & pairs.brn, "score"] = 4
    pairs.loc[pairs.addr, "score"] = 5                      # (정확/음역 이름) + 사업자번호6 + 시군구
    pairs = pairs[pairs.score > 0]

    top = pairs.groupby("wp_id")["score"].transform("max")
    best = pairs[pairs["score"] == top]
    g = best.groupby("wp_id").agg(score=("score", "first"), ncorp=("corp_code", "nunique"), corp_code=("corp_code", "first"), exact=("exact", "max"))
    ev = {5: "name+brn6+sigungu", 4: "name+brn6;addr_mismatch_or_unknown", 3: "alias_name+brn6",
          2: "name_only;brn6_mismatch(공장·지점 가능, 합산 금지)"}
    g["grade"] = g["score"].map({5: "high_confidence", 4: "candidate", 3: "candidate", 2: "candidate"})
    amb = g["ncorp"] > 1
    g.loc[amb, "grade"] = "ambiguous"
    g["evidence"] = g["score"].map(ev)
    g.loc[(g["score"] == 5) & ~g["exact"].astype(bool), "evidence"] = "alias_name+brn6+sigungu"
    g["evidence"] = g["evidence"] + g["ncorp"].map(lambda c: "" if c == 1 else f";dart_candidates={c}")
    g.loc[amb, "corp_code"] = None
    res = g.reset_index()[["wp_id", "corp_code", "grade", "evidence", "score"]]
    rest = n.loc[~n["wp_id"].isin(res["wp_id"]), ["wp_id"]].assign(corp_code=None, grade="unmatched", evidence="no_name_match", score=0)
    res = pd.concat([res, rest], ignore_index=True)

    if overrides is not None and len(overrides):
        key = n[["wp_id", "brn6", "name_norm"]].merge(overrides, on=["brn6", "name_norm"], how="inner")
        for _, r in key.iterrows():
            res.loc[res.wp_id == r["wp_id"], ["corp_code", "grade", "evidence", "score"]] = [r["corp_code"], "verified", f"manual_override:{r['evidence']}", 6]
    return res


# 단위 오류 방지: 일부 법인은 급여를 천원 단위로 공시한다(평균 7만 등). 현실적 범위를 벗어나면 임의 보정 없이 계산 불가로 둔다.
AVG_MIN, AVG_MAX = 10_000_000, 2_000_000_000
TOTAL_NAMES = ["성별합계", "합계", "소계", "총계", "전체", "전사", "계"]


def _num(s):
    s = str(s).replace(",", "").strip()
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def parse_emp(j: dict) -> dict | None:
    """직원현황 응답 → 법인 단위 요약(파생값). 실제 응답은 (사업부문 × 성별) 행마다 급여가 있거나, 합계성 행(성별합계·전사 등)에만 있다.
    1) 합계성 이름의 행 묶음을 우선순위 순으로 보고, 인원·급여가 모두 숫자인 첫 묶음을 쓴다(부분 행과 합계 행을 함께 더하지 않음).
    2) 없으면 모든 행이 완전할 때만 전체 행을 합산한다. 3) 그래도 안 되면 계산 불가(0으로 채우지 않음).
    일관성: 행별 보고된 1인 평균의 가중평균과 (급여총액÷인원)이 5% 넘게 다르면 consistency 를 기록한다."""
    if j.get("status") != "000":
        return None
    df = pd.DataFrame(j["list"])
    for c, src in (("sm_n", "sm"), ("tot_n", "fyer_salary_totamt"), ("avg_n", "jan_salary_am"), ("ten_n", "avrg_cnwk_sdytrn")):
        df[c] = df[src].map(_num)
    base = {"corp_code": df["corp_code"].iloc[0], "rcept_no": df["rcept_no"].iloc[0], "stlm_dt": df["stlm_dt"].iloc[0]}

    def complete(g):
        return len(g) > 0 and g["sm_n"].notna().all() and g["tot_n"].notna().all() and (g["sm_n"] > 0).all() and (g["tot_n"] > 0).all()

    chosen, basis = None, None
    for name in TOTAL_NAMES:
        g = df[df["fo_bbm"].astype(str).str.strip() == name]
        if complete(g):
            chosen, basis = g, name
            break
    if chosen is None and complete(df):
        chosen, basis = df, "모든 행"
    if chosen is None:
        return {**base, "basis": "none", "rows": len(df), "usable": False, "reason": "missing_salary_or_headcount"}
    emp, tot = chosen["sm_n"].sum(), chosen["tot_n"].sum()
    if not (AVG_MIN <= tot / emp <= AVG_MAX):
        return {**base, "basis": basis, "rows": len(chosen), "usable": False, "reason": "implausible_value_unit_suspect", "avg_salary_raw": float(tot / emp)}
    out = {**base, "basis": basis, "rows": len(chosen), "usable": True, "reason": "", "employees": float(emp), "salary_total": float(tot),
           "avg_salary_derived": float(tot / emp), "consistency": None, "avg_tenure_weighted": None}
    if chosen["avg_n"].notna().all():
        w = float((chosen["avg_n"] * chosen["sm_n"]).sum() / emp)
        out["consistency"] = float(abs(tot / emp - w) / w) if w else None
    if chosen["ten_n"].notna().all():
        out["avg_tenure_weighted"] = float((chosen["ten_n"] * chosen["sm_n"]).sum() / emp)
    return out
