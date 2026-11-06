"""INSIGHT: 변화 탐지(기사 아이템 '후보') + 상태 관리 + 공개 검증. 탐지 결과는 확정된 뉴스가 아니다.
원칙: 계산 불가는 만들지 않는다 / 모든 후보에 근거 수치·조건·품질 경고·취재 필요사항을 붙인다 / published 만 사이트로 나간다."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import METHODOLOGY_VERSION
from .metrics import _group_label

CONFIG = Path(__file__).resolve().parents[2] / "config" / "insight_rules.yaml"
STATUSES = ("candidate", "reviewed", "published", "rejected")
SOURCE = "국민연금공단_국민연금 가입 사업장 내역(공공데이터포털 15083277)"
CAP_NEAR = 0.9

NEEDS = {
    "headcount_drop": ["같은 법인의 다른 사업장으로의 이동·통합 여부(사업장 재등록·분할 포함)", "실제 인원 감축인지, 납부예외·휴직 등 가입 상태 변화인지 회사 확인",
                       "사업 구조 변화(매각·폐업·이전)나 공시(사업보고서 직원 수)와의 대조"],
    "turnaround": ["감소기에 사업장 이동·재등록이 있었는지, 증가분이 신규 사업장 흡수인지 확인", "회사 설명과 공시 직원 수 흐름 대조"],
    "quiet_high_pay": ["국민연금 기준소득월액이 상여·성과급을 포함하지 않으므로 실제 급여 구조 확인", "소규모 사업장 특성(소수 고소득자·임원 가입)이 평균을 끌어올렸는지 확인",
                       "비교집단 업종 분류의 적절성 확인"],
    "industry_headcount_shift": ["사업장 신규 등록·소멸이 아닌 같은 사업장 집합의 변화임을 감안해 신규·소멸 사업장 별도 확인", "업종 분류 변경·사업장 통합 효과 확인", "통계청·고용부 업종별 고용 통계와 대조"],
    "pay_dispersion": ["상한 접근 사업장을 제외한 값이라 실제 격차는 더 클 수 있음 — 공시 급여로 대조", "특정 소수 사업장이 지표를 좌우하는지 확인", "업종 내 이질적 하위 업종 혼재 여부 확인"],
}


def load_rules(path: Path | None = None) -> dict:
    return yaml.safe_load(open(path or CONFIG, encoding="utf-8"))


def _num(x, nd=None):
    if x is None or (isinstance(x, (float, np.floating)) and not np.isfinite(x)):
        return None
    return round(float(x), nd) if nd is not None else int(round(float(x)))


def _series(P_S: pd.DataFrame, wp, ms):
    return [_num(v) for v in P_S.loc[wp, ms].tolist()]


def record(ym, typ, kind, sid, subject, metrics, comparison, warnings, conditions, score):
    return {"id": f"{ym}:{typ}:{kind}{sid}", "type": typ, "base_month": ym, "subject": subject, "metrics": metrics,
            "comparison": comparison, "quality_warnings": sorted(set(warnings)), "conditions": conditions,
            "reporting_needs": NEEDS[typ], "source": SOURCE, "status": "candidate", "score": _num(score, 4),
            "methodology_version": METHODOLOGY_VERSION}


def group_totals(S: pd.DataFrame, names: pd.Series, ms) -> dict:
    """같은 정규화 이름 사업장 묶음의 합계(첫 달, 마지막 달)와 사업장 수. 이동·통합 효과 판별용."""
    nm = names.reindex(S.index)
    ok = nm.notna()
    first, last = S[ms[0]].fillna(0)[ok].groupby(nm[ok]).sum(), S[ms[-1]].fillna(0)[ok].groupby(nm[ok]).sum()
    cnt = S[ms].notna().any(axis=1)[ok].groupby(nm[ok]).sum()
    return {"first": first, "last": last, "n": cnt}


def offset_flag(name: str, own_net: float, gt: dict, ratio: float) -> bool:
    """같은 이름 묶음이 2곳 이상이고 묶음 합계 변화가 개별 변화의 ratio 배 미만이면 사업장 이동 가능성."""
    if gt["n"].get(name, 0) < 2:
        return False
    group_net = gt["last"].get(name, 0) - gt["first"].get(name, 0)
    return abs(group_net) < ratio * abs(own_net)


def detect_headcount_drop(d, P, ms, rules, ym, gt, ind_growth):
    r, c = rules["detectors"]["headcount_drop"], rules["common"]
    S = P["subs"]
    base = d["subs"] - d["net_12m"]
    m = (d["history_complete"] & d["growth_12m"].notna() & (base >= r["min_base"]) & (d["growth_12m"] <= r["drop_pct"])
         & (d["net_12m"] <= r["min_net"]) & (d["status"] == "1"))
    if c["exclude_restructure_suspect"]:
        m &= ~d["restructure_suspect"].fillna(False)
    if c["exclude_project_sites"]:
        m &= ~d["project_site"].fillna(False)
    out = []
    for wp, x in d[m].sort_values("net_12m").head(r["limit"]).iterrows():
        warn = [f for f in (x["flags"] or "").split("|") if f in ("withdrawn", "dup_key")]
        if offset_flag(x["name_norm"], x["net_12m"], gt, c["group_offset_ratio"]):
            warn.append("possible_transfer_within_name_group")
        out.append(record(ym, "headcount_drop", "wp", int(wp),
                          {"kind": "workplace", "id": int(wp), "name": x["name_raw"], "industry": x["industry_name"], "loc": x["addr_jibun"]},
                          {"current": _num(x["subs"]), "previous": _num(base[wp]), "change_pct": _num(x["growth_12m"], 4), "net": _num(x["net_12m"]),
                           "series": _series(S, wp, ms), "months": ms, "lost_cum_12m": _num(x["lost_cum_12m"], 4)},
                          {"industry_total_growth_12m": _num(ind_growth.get(x["ind4"]), 4), "group": "같은 업종(코드 4자리) 계속 사업장 합계(사업장 30곳 이상일 때만)"},
                          warn, {"rule": "headcount_drop", **r}, abs(x["net_12m"])))
    return out


def detect_turnaround(d, P, ms, rules, ym, gt):
    r, c = rules["detectors"]["turnaround"], rules["common"]
    if len(ms) < 13:
        return []
    S = P["subs"]
    s0, s6, s9, s12 = S[ms[0]], S[ms[6]], S[ms[9]], S[ms[12]]
    full = S[ms].notna().all(axis=1)
    cond = (full & (s0 >= r["min_base"]) & ((s6 / s0 - 1) <= r["first_half_drop"]) & ((s12 / s6 - 1) >= r["second_half_gain"]) & (s12 > s9) & (s9 >= s6)
            & ((s0 - s6) >= r["min_swing_abs"]) & ((s12 - s6) >= r["min_swing_abs"]))
    idx = cond[cond].index.intersection(d.index)
    dd = d.loc[idx]
    m = dd["status"] == "1"
    if c["exclude_restructure_suspect"]:
        m &= ~dd["restructure_suspect"].fillna(False)
    if c["exclude_project_sites"]:
        m &= ~dd["project_site"].fillna(False)
    out = []
    gain = (s12 / s6 - 1)
    for wp, x in dd[m].assign(_g=gain.reindex(dd[m].index)).sort_values("_g", ascending=False).head(r["limit"]).iterrows():
        net_second = s12[wp] - s6[wp]
        warn = []
        if offset_flag(x["name_norm"], net_second, gt, c["group_offset_ratio"]):
            warn.append("possible_transfer_within_name_group")
        out.append(record(ym, "turnaround", "wp", int(wp),
                          {"kind": "workplace", "id": int(wp), "name": x["name_raw"], "industry": x["industry_name"], "loc": x["addr_jibun"]},
                          {"first_half_change_pct": _num(s6[wp] / s0[wp] - 1, 4), "second_half_change_pct": _num(s12[wp] / s6[wp] - 1, 4),
                           "start": _num(s0[wp]), "trough": _num(s6[wp]), "current": _num(s12[wp]), "series": _series(S, wp, ms), "months": ms},
                          {"window": f"{ms[0]}→{ms[6]}→{ms[12]}"}, warn, {"rule": "turnaround", **r}, x["_g"]))
    return out


def detect_quiet_high_pay(d, ms, rules, ym, overall_median):
    r, c = rules["detectors"]["quiet_high_pay"], rules["common"]
    m = (d["pay_public"] & d["peer_scope"].isin(r["need_scope"]) & d["subs"].between(r["min_subs"], r["max_subs"])
         & (d["pay_premium"] >= r["min_premium"]) & (d["pay_pct"] >= r["min_pct"]) & ~d["cap_flag"].fillna(False)
         & ~d["pay_censored"].fillna(False) & (d["grade"] == "B") & (d["peer_median"] >= r["min_peer_median_ratio"] * overall_median))
    if c["exclude_project_sites"]:
        m &= ~d["project_site"].fillna(False)
    if c["exclude_restructure_suspect"]:
        m &= ~d["restructure_suspect"].fillna(False)
    out = []
    for wp, x in d[m].sort_values("pay_premium", ascending=False).head(r["limit"]).iterrows():
        out.append(record(ym, "quiet_high_pay", "wp", int(wp),
                          {"kind": "workplace", "id": int(wp), "name": x["name_raw"], "industry": x["industry_name"], "loc": x["addr_jibun"]},
                          {"est_annual": _num(x["est_annual"]), "premium": _num(x["pay_premium"], 4), "percentile": _num(x["pay_pct"], 4),
                           "subs": _num(x["subs"]), "cap_ratio": _num(x["cap_ratio"], 3), "estimate_kind": "estimated(국민연금 기준소득월액 연환산)"},
                          {"peer_n": _num(x["peer_n"]), "peer_median": _num(x["peer_median"]), "peer_scope": x["peer_scope"], "peer_label": x["peer_label"], "base_month": ym},
                          ["estimate_not_reported_salary"], {"rule": "quiet_high_pay", **r}, x["pay_premium"]))
    return out


def industry_labels(d: pd.DataFrame, level: str) -> pd.Series:
    return d.groupby(level)["industry_name"].agg(_group_label)


def detect_industry_shift(d, P, ms, rules, ym, attrs):
    r, c = rules["detectors"]["industry_headcount_shift"], rules["common"]
    S = P["subs"]
    lv = r["level"]
    a = attrs.copy()
    a["ind4"] = a["industry_code"].fillna("").str[:4]
    a["ps"] = a["project_site"].fillna(False)
    S0, St = S[ms[0]], S[ms[-1]]
    cont = S0.notna() & St.notna() & ~a["ps"].reindex(S.index).fillna(False)
    grp = a["ind4"].reindex(S.index)
    ok = cont & grp.notna() & (grp != "") & ~grp.isin(["9999", "0000"])
    base = S0[ok].groupby(grp[ok]).sum()
    cur = St[ok].groupby(grp[ok]).sum()
    n = ok[ok].groupby(grp[ok]).size()
    ent = (S0.isna() & St.notna())[grp.notna()].groupby(grp[grp.notna()]).sum()
    ext = (S0.notna() & St.isna())[grp.notna()].groupby(grp[grp.notna()]).sum()
    tab = pd.DataFrame({"base": base, "cur": cur, "n": n}).dropna()
    tab = tab[(tab["base"] >= r["min_base_subs"]) & (tab["n"] >= r["min_continuing_wp"])]
    tab["net"], tab["pct"] = tab["cur"] - tab["base"], tab["cur"] / tab["base"] - 1
    labels = industry_labels(d.assign(ind4=d["industry_code"].fillna("").str[:4]), "ind4") if "ind4" not in d else industry_labels(d, "ind4")
    out = []
    for side, srt in (("increase", tab.sort_values("net", ascending=False)), ("decrease", tab.sort_values("net"))):
        for code, x in srt.head(r["limit"]).iterrows():
            out.append(record(ym, "industry_headcount_shift", "ind", f"{code}-{side}",
                              {"kind": "industry", "id": code, "name": labels.get(code, code), "direction": side},
                              {"base": _num(x["base"]), "current": _num(x["cur"]), "net": _num(x["net"]), "change_pct": _num(x["pct"], 4),
                               "continuing_workplaces": _num(x["n"]), "entrants": _num(ent.get(code, 0)), "exiters": _num(ext.get(code, 0)),
                               "window": f"{ms[0]}→{ms[-1]}"},
                              {"basis": "두 시점 모두 존재한 사업장 집합(신규·소멸 사업장 제외)"},
                              ["continuing_set_only"], {"rule": "industry_headcount_shift", **r}, abs(x["net"])))
    return out, tab, labels


def detect_pay_dispersion(d, P, ms, rules, ym, attrs, labels):
    r = rules["detectors"]["pay_dispersion"]
    S, E, C = P["subs"], P["est_m"] * 12, P["cap"]
    a = attrs
    grp = a["industry_code"].fillna("").str[:4].reindex(S.index)
    ps = a["project_site"].fillna(False).reindex(S.index).fillna(False)
    m0, mt = ms[0], ms[-1]
    ok = (S[m0] >= 10) & (S[mt] >= 10) & E[m0].notna() & E[mt].notna() & (C[m0] < CAP_NEAR) & (C[mt] < CAP_NEAR) & ~ps & grp.notna() & (grp != "") & ~grp.isin(["9999", "0000"])
    rows = []
    for code, idx in ok[ok].groupby(grp[ok]).groups.items():
        if len(idx) < r["min_wp"]:
            continue
        e0, et = E.loc[idx, m0], E.loc[idx, mt]
        q0, qt = e0.quantile([.1, .5, .9]).values, et.quantile([.1, .5, .9]).values
        rows.append({"code": code, "n": len(idx), "p10_0": q0[0], "p90_0": q0[2], "p10_t": qt[0], "p90_t": qt[2], "med_0": q0[1], "med_t": qt[1],
                     "ratio0": q0[2] / q0[0], "ratio_t": qt[2] / qt[0]})
    tab = pd.DataFrame(rows)
    out = []
    if tab.empty:
        return out, tab
    tab["change"] = tab["ratio_t"] / tab["ratio0"] - 1
    for _, x in tab[tab["change"] >= r["min_change"]].sort_values("change", ascending=False).head(r["limit"]).iterrows():
        out.append(record(ym, "pay_dispersion", "ind", x["code"],
                          {"kind": "industry", "id": x["code"], "name": labels.get(x["code"], x["code"])},
                          {"ratio_p90_p10_start": _num(x["ratio0"], 3), "ratio_p90_p10_end": _num(x["ratio_t"], 3), "change_pct": _num(x["change"], 4),
                           "p10_start": _num(x["p10_0"]), "p90_start": _num(x["p90_0"]), "p10_end": _num(x["p10_t"]), "p90_end": _num(x["p90_t"]),
                           "median_start": _num(x["med_0"]), "median_end": _num(x["med_t"]), "workplaces": _num(x["n"]), "window": f"{m0}→{mt}",
                           "estimate_kind": "estimated(국민연금 기준소득월액 연환산)"},
                          {"basis": "두 시점 모두 가입자 10명 이상·상한 비접근(cap<0.9)인 같은 사업장 집합"},
                          ["cap_near_excluded_true_dispersion_may_be_larger", "estimate_not_reported_salary"], {"rule": "pay_dispersion", **r}, x["change"]))
    return out, tab


# ---------------------------------------------------------------- 상태 관리·공개 검증
def read_status(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=["id", "status", "reviewer", "date", "note"])
    s = pd.read_csv(path, dtype=str).fillna("")
    bad = s[~s["status"].isin(STATUSES)]
    if len(bad):
        raise ValueError(f"알 수 없는 상태: {bad['status'].tolist()}")
    return s


def merge_status(cands: list[dict], status: pd.DataFrame) -> list[dict]:
    st = status.drop_duplicates("id", keep="last").set_index("id")
    out = []
    for c in cands:
        c = dict(c)
        if c["id"] in st.index:
            c["status"] = st.loc[c["id"], "status"]
            c["review"] = {"reviewer": st.loc[c["id"], "reviewer"], "date": st.loc[c["id"], "date"], "note": st.loc[c["id"], "note"]}
        out.append(c)
    return out


_FM = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
REQUIRED = ("title", "why", "what", "how", "so_what", "evidence", "published_at")


def parse_article(path: Path) -> dict:
    m = _FM.match(Path(path).read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: front matter(---) 가 없습니다")
    meta = yaml.safe_load(m.group(1)) or {}
    meta["body"] = m.group(2).strip()
    meta["slug"] = Path(path).stem
    return meta


def build_published(cands: list[dict], status: pd.DataFrame, content_dir: Path) -> list[dict]:
    """status 가 published 인 후보만, 사람이 쓴 WHY/WHAT/HOW/SO WHAT 기사와 근거가 모두 갖춰졌을 때 공개 JSON 으로 만든다."""
    byid = {c["id"]: c for c in cands}
    out = []
    pub = status[status["status"] == "published"].drop_duplicates("id", keep="last")
    seen_articles = set()
    for _, row in pub.iterrows():
        cid = row["id"]
        if cid not in byid:
            raise ValueError(f"published 후보 {cid} 가 후보 목록에 없습니다")
        arts = [p for p in Path(content_dir).glob("*.md") if cid in parse_article(p).get("evidence", [])]
        if not arts:
            raise ValueError(f"published 후보 {cid} 를 근거로 하는 기사(content/insights/*.md)가 없습니다")
        for p in arts:
            if p.stem in seen_articles:
                continue
            a = parse_article(p)
            miss = [k for k in REQUIRED if not a.get(k)]
            if miss:
                raise ValueError(f"{p.name}: 필수 항목 누락 {miss}")
            ev = []
            for e in a["evidence"]:
                if e not in byid:
                    raise ValueError(f"{p.name}: 근거 {e} 가 후보 목록에 없습니다")
                ev_row = status[status["id"] == e]
                if ev_row.empty or ev_row.iloc[-1]["status"] != "published":
                    raise ValueError(f"{p.name}: 근거 {e} 의 상태가 published 가 아닙니다")
                c = byid[e]
                ev.append({k: c[k] for k in ("id", "type", "base_month", "subject", "metrics", "comparison", "quality_warnings", "source")})
            seen_articles.add(p.stem)
            out.append({"slug": a["slug"], "title": a["title"], "why": a["why"], "what": a["what"], "how": a["how"], "so_what": a["so_what"],
                        "body": a["body"], "published_at": str(a["published_at"]), "evidence": ev})
    return out
