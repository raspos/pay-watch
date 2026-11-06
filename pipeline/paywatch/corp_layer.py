"""법인(회사) 단위 레이어: 확인된 사업장 합산(NPS) + DART 직원현황(공시, 파생값) + 공시 비교집단.
원칙: high_confidence/verified 사업장만 합산 / 후보·모호한 사업장은 합산하지 않음 / 급여는 매칭에 쓰지 않음 /
      공시값(derived)과 추정값(estimated)은 별도 필드 / 계산 불가는 None."""
from __future__ import annotations

import glob
import json
import math
import os

import numpy as np
import pandas as pd

from .company_matcher import addr_key, parse_emp
from .dart_client import CACHE
from .tables import load_caps, lookup

CONFIRMED = ("high_confidence", "verified")
CONSISTENCY_OK = 0.05
PEER_MIN = 30
PEER_TOP = 30          # 공시 비교집단별로 내보내는 상위 목록 길이
SIZE_BINS = [0, 100, 300, 1000, 5000, 10**9]
SIZE_LABELS = ["100명 미만", "100~299명", "300~999명", "1,000~4,999명", "5,000명 이상"]
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="


def load_emp_table(year: str = "2025") -> pd.DataFrame:
    """캐시된 직원현황(사업보고서) 파싱 결과. 013(없음)은 제외하고 별도 카운트로 센다."""
    rows, nodata = [], 0
    for p in glob.glob(os.path.join(str(CACHE), "empSttus", f"*_{year}_11011.json")):
        j = json.load(open(p, encoding="utf-8"))
        if j.get("status") != "000":
            nodata += 1
            continue
        r = parse_emp(j)
        if r:
            rows.append(r)
    t = pd.DataFrame(rows)
    t.attrs["nodata"] = nodata
    return t


def peer_hist(v: pd.Series, bins: int = 20) -> dict:
    """공시 비교집단 분포: 2~98% 범위를 20구간으로(양 끝은 범위로 모음). 합계는 표본 수와 같다."""
    lo, hi = float(v.quantile(.02)), float(v.quantile(.98))
    if hi <= lo:
        hi = lo + 1.0
    counts, edges = np.histogram(v.clip(lo, hi), bins=bins, range=(lo, hi))
    return {"lo": int(round(lo)), "step": int(round((hi - lo) / bins)), "counts": [int(c) for c in counts]}


def dart_peers(emp: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    """공시 비교집단: DART 업종코드 3자리 → 2자리, × 직원 규모. 일관성 통과 법인만, 표본 30 미만이면 비교하지 않는다."""
    e = emp[emp["usable"] & emp["consistency"].notna() & (emp["consistency"] <= CONSISTENCY_OK)].copy()
    e = e.merge(comp[["corp_code", "induty_code", "corp_name"]], on="corp_code", how="left")
    e["ind3"], e["ind2"] = e["induty_code"].fillna("").str[:3], e["induty_code"].fillna("").str[:2]
    e["size"] = pd.cut(e["employees"], SIZE_BINS, labels=SIZE_LABELS, right=False)
    out = pd.DataFrame(index=e["corp_code"], columns=["peer_n", "peer_median", "peer_p25", "peer_p75", "top_pct", "level", "size", "hist", "gkey"], dtype=object)
    done = set()
    groups: dict = {}
    for level, key in ((3, "ind3"), (2, "ind2")):
        for (code, size), g in e[e[key] != ""].groupby([key, "size"], observed=True):
            todo = g[~g["corp_code"].isin(done)]
            if len(g) < PEER_MIN or todo.empty:
                continue
            v = g["avg_salary_derived"]
            hist = peer_hist(v)
            top = g.sort_values("avg_salary_derived", ascending=False).head(PEER_TOP)
            groups[f"{level}:{code}:{size}"] = {"n": int(len(g)), "level": level, "code": code, "size": str(size),
                                                "label": f"DART 업종코드 앞 {level}자리 {code}, 직원 {size}",
                                                "items": [[r2["corp_code"], r2["corp_name"], int(round(r2["avg_salary_derived"])), int(round(r2["employees"]))] for _, r2 in top.iterrows()]}
            for _, r in todo.iterrows():
                higher = float((v > r["avg_salary_derived"]).sum())
                out.loc[r["corp_code"]] = [len(g), v.median(), v.quantile(.25), v.quantile(.75), max(1, math.ceil(higher / len(g) * 100)), level, str(size), hist, f"{level}:{code}:{size}"]
                done.add(r["corp_code"])
    res = out.dropna(subset=["peer_n"]).copy()
    gids = {k: i for i, k in enumerate(sorted(groups))}
    res["gid"] = res["gkey"].map(gids)
    res.attrs["groups"] = {str(gids[k]): v for k, v in groups.items()}
    return res


def _arr(s):
    return [None if pd.isna(x) else int(round(float(x))) for x in s]


class PanelArrays:
    """패널(와이드 DataFrame)을 넘파이 배열로 한 번만 꺼내 둔다. 법인마다 .loc 로 재색인하면 법인당 ~0.5초가 걸린다."""

    def __init__(self, P: dict, ms: list[str]):
        self.index = P["subs"].index
        self.ms = ms
        self.S, self.E, self.A, self.L = (P[k][ms].to_numpy(dtype=float) for k in ("subs", "est_m", "acq", "lost"))


def _nansum0(x):
    out = np.nansum(x, axis=0)
    return np.where(np.isnan(x).all(axis=0), np.nan, out)


def aggregate_corp(code: str, wps: list[int], P, ms: list[str], d: pd.DataFrame, caps: pd.DataFrame) -> dict:
    """확인된 사업장들의 월별 합계. 급여 추정은 가입자 10명 이상 사업장만 가입자 가중평균(고지액÷요율은 가중평균으로 소거됨)."""
    PA = P if isinstance(P, PanelArrays) else PanelArrays(P, ms)
    rows = PA.index.get_indexer(wps)
    rows = rows[rows >= 0]
    S, E, A, L = PA.S[rows], PA.E[rows], PA.A[rows], PA.L[rows]
    subs = _nansum0(S)
    ok = (S >= 10) & ~np.isnan(E)
    w = np.where(ok, S, 0.0)
    sw = w.sum(axis=0)
    est_m = np.where(sw >= 10, (np.where(ok, E, 0.0) * w).sum(axis=0) / np.where(sw > 0, sw, 1.0), np.nan)
    cap = np.array([lookup(caps, m, "upper_cap") or np.nan for m in ms], dtype=float)
    g12 = net12 = None
    if len(ms) >= 13:
        both = ~np.isnan(S[:, -1]) & ~np.isnan(S[:, -13])
        base = S[both, -13].sum() if both.any() else 0.0
        if base >= 50:
            g12, net12 = float(S[both, -1].sum() / base - 1), float(S[both, -1].sum() - base)
    prim = int(PA.index[rows[int(np.nanargmax(np.where(np.isnan(S[:, -1]), -1, S[:, -1])))]])
    mk = lambda v: pd.Series(v, index=ms)
    return {"subs": mk(subs), "est_annual": mk(est_m * 12), "cap_ratio": mk(est_m / cap), "acq": mk(_nansum0(A)), "lost": mk(_nansum0(L)),
            "g12": g12, "net12": net12, "primary": prim, "n_wp": len(rows)}


def build_corp_records(res: pd.DataFrame, comp: pd.DataFrame, emp: pd.DataFrame, P: dict, ms: list[str], d: pd.DataFrame) -> list[dict]:
    caps = load_caps()
    PA = PanelArrays(P, ms)
    conf = res[res["grade"].isin(CONFIRMED) & res["corp_code"].notna()]
    set_idx = set(PA.index.tolist())
    peers = dart_peers(emp, comp) if len(emp) else pd.DataFrame()
    cdict = comp.set_index("corp_code").to_dict("index")
    edict = emp.set_index("corp_code").to_dict("index") if len(emp) else {}
    out = []
    for code, g in conf.groupby("corp_code"):
        wps = [w for w in g["wp_id"].tolist() if w in set_idx]
        if not wps or code not in cdict:
            continue
        a = aggregate_corp(code, wps, PA, ms, d, caps)
        c, e = cdict[code], edict.get(code)
        pw = d.loc[a["primary"]] if a["primary"] in d.index else None
        dart = None
        if e is not None and e.get("usable"):
            lvl = "ok" if (e["consistency"] is not None and e["consistency"] <= CONSISTENCY_OK) else ("caution" if e["consistency"] is not None else "unverified")
            pr = peers.loc[code] if len(peers) and code in peers.index else None
            dart = {"fy": 2025, "employees": int(round(e["employees"])), "avg": int(round(e["avg_salary_derived"])), "total": int(round(e["salary_total"])),
                    "tenure": None if e["avg_tenure_weighted"] is None else round(float(e["avg_tenure_weighted"]), 1),
                    "consistency": None if e["consistency"] is None else round(float(e["consistency"]), 4), "level": lvl, "basis": e["basis"],
                    "stlm": e["stlm_dt"], "src": DART_URL + str(e["rcept_no"]), "kind": "derived",
                    "pos": None if pr is None or lvl != "ok" else {"top_pct": int(pr["top_pct"]), "n": int(pr["peer_n"]), "median": int(round(pr["peer_median"])),
                                                                  "p25": int(round(pr["peer_p25"])), "p75": int(round(pr["peer_p75"])), "level": int(pr["level"]), "size": pr["size"], "hist": pr["hist"], "gid": int(pr["gid"])}}
        subs_t = float(a["subs"].iloc[-1]) if pd.notna(a["subs"].iloc[-1]) else None
        est_t = a["est_annual"].iloc[-1]
        nps = {"est": None if pd.isna(est_t) else int(round(est_t)), "cap": None if pd.isna(a["cap_ratio"].iloc[-1]) else round(float(a["cap_ratio"].iloc[-1]), 3),
               "subs": None if subs_t is None else int(subs_t), "g12": None if a["g12"] is None else round(a["g12"], 4), "net12": None if a["net12"] is None else int(round(a["net12"])),
               "series": {"subs": _arr(a["subs"]), "est": _arr(a["est_annual"]), "cap": [None if pd.isna(x) else round(float(x), 3) for x in a["cap_ratio"]],
                          "acq": _arr(a["acq"]), "lost": _arr(a["lost"])}, "kind": "estimated"}
        pos_nps = None
        if pw is not None and pd.notna(pw.get("peer_n")) and pw.get("pay_public"):
            pos_nps = {"premium": None if pd.isna(pw.get("pay_premium")) else round(float(pw["pay_premium"]), 4), "pct": None if pd.isna(pw.get("pay_pct")) else round(float(pw["pay_pct"]), 4),
                       "n": int(pw["peer_n"]), "label": pw.get("peer_label"), "censored": bool(pw.get("pay_censored")), "basis_wp": int(a["primary"]),
                       "gid": None if pd.isna(pw.get("peer_gid")) else int(pw["peer_gid"]), "est": None if pd.isna(pw.get("est_annual")) else int(round(pw["est_annual"])),
                       "cap": None if pd.isna(pw.get("cap_ratio")) else round(float(pw["cap_ratio"]), 3)}
        scope = None if (dart is None or subs_t is None) else round(subs_t / dart["employees"], 3)
        basis = "dart" if (dart and dart["level"] == "ok") else "nps"
        wl = sorted(({"id": int(w), "n": d.loc[w, "name_raw"], "loc": d.loc[w, "addr_jibun"], "subs": None if pd.isna(d.loc[w, "subs"]) else int(d.loc[w, "subs"]),
                      "pp": bool(d.loc[w, "pay_public"])} for w in wps if w in d.index), key=lambda x: -(x["subs"] or 0))
        out.append({"code": code, "n": c["corp_name"], "mk": c.get("corp_cls"), "listed": bool(c.get("stock_code")), "ind": c.get("induty_code"),
                    "loc": None if pw is None else pw["addr_jibun"], "primary": int(a["primary"]), "ym": ms[-1], "months": ms, "basis": basis, "dart": dart, "nps": nps,
                    "pos_nps": pos_nps, "scope": scope, "n_wp": a["n_wp"], "wps": wl[:30],
                    "match": {"grades": sorted(set(g["grade"])), "evidence": sorted(set(g["evidence"]))}})
    return out
