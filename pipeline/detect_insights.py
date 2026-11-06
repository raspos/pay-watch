"""Stage 5: 변화 탐지(후보) + 월간 리포트 + 산업 집계(공개용) 생성. NPS 13개월만 사용(DART 불필요).
산출: insights/candidates/YYYY-MM.json(내부), reports/insights/candidates_YYYY-MM.md(취재용), reports/monthly/YYYY-MM.{md,json},
      site/data/insights/{trends,published}.json (공개: 산업 단위 집계와 사람이 승인한 콘텐츠만)"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch import insights as I  # noqa: E402
from paywatch.metrics import is_project_site, load_panel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data/interim"
TYPE_KO = {"headcount_drop": "사람이 줄어드는 회사", "turnaround": "반전의 직장", "quiet_high_pay": "조용한 연봉 맛집",
           "industry_headcount_shift": "고용의 지각변동", "pay_dispersion": "연봉 양극화"}


def build_attrs(ms):
    """wp_id 별 마지막 등장 시점의 속성(소멸 사업장 포함)."""
    attrs = None
    for ym in ms:
        c = pd.read_parquet(INTERIM / f"nps_{ym}.parquet", columns=["name_raw", "name_norm", "industry_code", "industry_name", "status", "subscribers"])
        c.index = pd.read_parquet(INTERIM / f"ids_{ym}.parquet")["wp_id"].values
        c["project_site"] = is_project_site(c["name_raw"])
        attrs = c if attrs is None else pd.concat([attrs[~attrs.index.isin(c.index)], c])
    return attrs


def fmt(v, kind="int"):
    if v is None:
        return "—"
    return f"{v*100:+.1f}%" if kind == "pct" else (f"{v:,.0f}" if kind == "int" else str(v))


def main():
    rules = I.load_rules()
    ms = sorted(p.split("nps_")[1][:7] for p in glob.glob(str(INTERIM / "nps_20*.parquet")))
    assert len(ms) == 13
    ym = ms[-1]
    P = load_panel(INTERIM, ms)
    d = pd.read_parquet(INTERIM / f"metrics_{ym}.parquet")
    attrs = build_attrs(ms)
    gt = I.group_totals(P["subs"], attrs["name_norm"], ms)
    # 업종(4자리) 전체 합계 증감률: 두 시점 모두 존재한 사업장 집합(현장 단위 제외), 사업장 30곳 이상
    S = P["subs"]
    a4 = attrs["industry_code"].fillna("").str[:4].reindex(S.index)
    cont = S[ms[0]].notna() & S[ms[-1]].notna() & ~attrs["project_site"].reindex(S.index).fillna(False) & (a4 != "")
    gs = pd.DataFrame({"b": S[ms[0]][cont].groupby(a4[cont]).sum(), "c": S[ms[-1]][cont].groupby(a4[cont]).sum(), "n": cont[cont].groupby(a4[cont]).size()})
    gs = gs[(gs["n"] >= 30) & (gs["b"] > 0)]
    ind_growth = (gs["c"] / gs["b"] - 1).to_dict()
    overall_median = d.loc[d["pay_public"] & ~d["project_site"], "est_annual"].median()

    cands = []
    cands += I.detect_headcount_drop(d, P, ms, rules, ym, gt, ind_growth)
    cands += I.detect_turnaround(d, P, ms, rules, ym, gt)
    cands += I.detect_quiet_high_pay(d, ms, rules, ym, overall_median)
    shift, shift_tab, labels = I.detect_industry_shift(d, P, ms, rules, ym, attrs)
    disp, disp_tab = I.detect_pay_dispersion(d, P, ms, rules, ym, attrs, labels)
    cands += shift + disp

    status = I.read_status(ROOT / "insights/status.csv")
    cands = I.merge_status(cands, status)
    (ROOT / "insights/candidates").mkdir(parents=True, exist_ok=True)
    (ROOT / f"insights/candidates/{ym}.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    write_candidates_md(cands, ym, rules)
    write_monthly(d, P, ms, attrs, labels, ym)
    write_site(P, ms, shift_tab, disp_tab, labels, cands, status, ym)
    cnt = pd.Series([c["type"] for c in cands]).value_counts().to_dict()
    print("candidates", len(cands), cnt)


def write_candidates_md(cands, ym, rules):
    L = [f"# INSIGHT 후보 — {ym} (내부 취재용, 비공개)", "",
         "※ **자동 탐지 결과는 확정된 뉴스가 아니다.** 가입자 수 변화는 사업장 재등록·이동·통합, 납부예외 등으로도 생길 수 있고, 추정급여는 국민연금 기준소득월액 역산값이다. 각 후보의 '취재 필요사항'을 확인하기 전에는 공개하지 않는다.",
         "상태 변경: `insights/status.csv`에 `id,status,reviewer,date,note` 추가(candidate→reviewed→published/rejected).", ""]
    L += ["## 자료가 없어 만들지 않은 탐지기", ""] + [f"- **{u['name']}**: 필요 자료 — {u['need']}" for u in rules["unavailable"]] + [""]
    for typ, ko in TYPE_KO.items():
        cs = [c for c in cands if c["type"] == typ]
        L += [f"## {ko} ({len(cs)}건)", ""]
        for c in cs[:15]:
            m, s = c["metrics"], c["subject"]
            if typ == "headcount_drop":
                line = f"{s['name']} · {s['industry']} · {s['loc']} — {fmt(m['previous'])}→{fmt(m['current'])}명({fmt(m['change_pct'],'pct')}, 순 {fmt(m['net'])}), 업종 합계 {fmt(c['comparison']['industry_total_growth_12m'],'pct')}"
            elif typ == "turnaround":
                line = f"{s['name']} · {s['industry']} — {fmt(m['start'])}→{fmt(m['trough'])}→{fmt(m['current'])}명(전반 {fmt(m['first_half_change_pct'],'pct')}, 후반 {fmt(m['second_half_change_pct'],'pct')})"
            elif typ == "quiet_high_pay":
                line = f"{s['name']} · {s['industry']} · 가입자 {fmt(m['subs'])}명 — 추정 {fmt(m['est_annual'])}원, 비교집단({c['comparison']['peer_label']}, {fmt(c['comparison']['peer_n'])}곳) 중앙값 대비 {fmt(m['premium'],'pct')}"
            elif typ == "industry_headcount_shift":
                line = f"{s['name']}({s['id']}, {s['direction']}) — {fmt(m['base'])}→{fmt(m['current'])}명({fmt(m['change_pct'],'pct')}, 순 {fmt(m['net'])}), 계속 사업장 {fmt(m['continuing_workplaces'])}곳, 신규 {fmt(m['entrants'])}·소멸 {fmt(m['exiters'])}곳"
            else:
                line = f"{s['name']}({s['id']}) — P90/P10 {m['ratio_p90_p10_start']}→{m['ratio_p90_p10_end']}({fmt(m['change_pct'],'pct')}), 사업장 {fmt(m['workplaces'])}곳"
            w = f" ⚠ {', '.join(c['quality_warnings'])}" if c["quality_warnings"] else ""
            L.append(f"- `{c['id']}` {line}{w}")
        L += ["", f"취재 필요사항: " + " / ".join(I.NEEDS[typ]), ""]
    out = ROOT / f"reports/insights/candidates_{ym}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")


def write_monthly(d, P, ms, attrs, labels, ym):
    prev = ms[-2]
    S, E, C = P["subs"], P["est_m"] * 12, P["cap"]
    cur = pd.read_parquet(INTERIM / f"nps_{ym}.parquet", columns=["status", "subscribers", "flags"])
    cur.index = pd.read_parquet(INTERIM / f"ids_{ym}.parquet")["wp_id"].values
    pv = pd.read_parquet(INTERIM / f"nps_{prev}.parquet", columns=["status", "subscribers", "name_raw", "pay_public"])
    pv.index = pd.read_parquet(INTERIM / f"ids_{prev}.parquet")["wp_id"].values
    ids_t = pd.read_parquet(INTERIM / f"ids_{ym}.parquet")
    new_ids = ids_t.loc[ids_t["link_tier"] == "new", "wp_id"]
    gone = pv[~pv.index.isin(cur.index)]
    new = cur.loc[cur.index.isin(new_ids)]
    L = [f"# PAY워치 월간 리포트 — {ym}", "", "※ 국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다. 아래 수치는 자동 집계이며 개별 기업에 대한 평가·단정이 아닙니다.", ""]
    J = {"base_month": ym, "prev_month": prev}
    L += ["## 1. 분석 대상", "", f"- 원본 행 수 {len(cur):,} / 검색 가능(등록·3명 이상) {int(d['search_visible'].sum()):,} / 추정급여 제공(10명 이상) {int(d['pay_public'].sum()):,}",
          f"- 전월({prev}) 대비 행 수 {len(cur)-len(pv):+,} ({(len(cur)/len(pv)-1)*100:+.2f}%), 가입자 합 {int(cur['subscribers'].sum()):,} (전월 대비 {(cur['subscribers'].sum()/pv['subscribers'].sum()-1)*100:+.2f}%)", ""]
    J["rows"] = {"current": len(cur), "prev": len(pv), "subs_current": int(cur["subscribers"].sum()), "subs_prev": int(pv["subscribers"].sum())}
    L += ["## 2. 신규 등장·자료에서 사라진 사업장", "",
          f"- **신규 등장** {len(new):,}곳 (등록 {int((new['status']=='1').sum()):,} / 탈퇴 행 {int((new['status']=='2').sum()):,} / 가입자 10명 이상 {int((new['subscribers']>=10).sum()):,}) — 신규 설립뿐 아니라 공개 범위(3명)·재등록·명칭 변경 영향이 섞여 있다.",
          f"- **자료에서 사라진 사업장** {len(gone):,}곳 (전월 탈퇴 행 {int((gone['status']=='2').sum()):,} / 전월 가입자 10명 이상 {int((gone['subscribers']>=10).sum()):,}) — **폐업을 뜻하지 않는다**: 공개 대상 기준 미달, 사업장명·법인 변경, 재등록 가능성이 있다.", ""]
    J["new"] = {"n": len(new), "active": int((new["status"] == "1").sum()), "ge10": int((new["subscribers"] >= 10).sum())}
    J["gone"] = {"n": len(gone), "was_withdrawn": int((gone["status"] == "2").sum()), "ge10": int((gone["subscribers"] >= 10).sum())}
    cont = S[prev].notna() & S[ym].notna() & ~attrs["project_site"].reindex(S.index).fillna(False)
    net = (S[ym] - S[prev])[cont]
    base = S[prev][cont]
    info = d[["name_raw", "industry_name", "restructure_suspect"]].reindex(net.index)
    def top(sr, asc, k=15):
        x = sr.sort_values(ascending=asc).head(k)
        return [{"id": int(i), "name": info.loc[i, "name_raw"], "industry": info.loc[i, "industry_name"], "net": int(v), "pct": float(v / base[i]) if base[i] else None,
                 "restructure_suspect": bool(info.loc[i, "restructure_suspect"])} for i, v in x.items() if pd.notna(info.loc[i, "name_raw"])]
    inc, dec = top(net, False), top(net, True)
    L += ["## 3. 가입자 수 증감 상위 사업장 (전월 대비, 같은 사업장 기준, 현장 단위 제외)", "", "| 구분 | 사업장 | 증감(명) | 증감률 | 비고 |", "|---|---|---|---|---|"]
    for lab, rows in (("증가", inc), ("감소", dec)):
        for r in rows[:10]:
            L.append(f"| {lab} | {r['name']} ({r['industry']}) | {r['net']:+,} | {fmt(r['pct'],'pct')} | {'급변 의심' if r['restructure_suspect'] else ''} |")
    J["top_increase"], J["top_decrease"] = inc, dec
    pc = d[d["pay_public"] & d["pay_change_12m"].notna() & (d["subs"] >= 50) & ~d["project_site"]]
    pu, pd_ = pc.sort_values("pay_change_12m", ascending=False).head(10), pc.sort_values("pay_change_12m").head(10)
    L += ["", "## 4. 추정급여 변화가 큰 사업장 (12개월, 상한 비접근, 가입자 50명 이상)", "", "※ 직원 구성 변화가 섞인 값이며 임금 인상률이 아니다.", "", "| 구분 | 사업장 | 변화율 |", "|---|---|---|"]
    for lab, df in (("상승", pu), ("하락", pd_)):
        for i, r in df.iterrows():
            L.append(f"| {lab} | {r['name_raw']} ({r['industry_name']}) | {fmt(r['pay_change_12m'],'pct')} |")
    J["pay_change_up"] = [{"id": int(i), "name": r["name_raw"], "v": float(r["pay_change_12m"])} for i, r in pu.iterrows()]
    J["pay_change_down"] = [{"id": int(i), "name": r["name_raw"], "v": float(r["pay_change_12m"])} for i, r in pd_.iterrows()]
    # 산업별
    grp = attrs["industry_code"].fillna("").str[:4].reindex(S.index)
    okg = cont & grp.notna() & (grp != "") & ~grp.isin(["9999", "0000"])
    t = pd.DataFrame({"base": S[prev][okg].groupby(grp[okg]).sum(), "cur": S[ym][okg].groupby(grp[okg]).sum(), "n": okg[okg].groupby(grp[okg]).size()})
    t = t[(t["base"] >= 3000)]
    t["net"], t["pct"] = t["cur"] - t["base"], t["cur"] / t["base"] - 1
    L += ["", "## 5. 산업별 가입자 증감 (전월 대비, 같은 사업장 기준, 업종코드 4자리, 기준 가입자 3,000명 이상)", "", "| 구분 | 업종 | 증감(명) | 증감률 | 사업장 |", "|---|---|---|---|---|"]
    ind_up, ind_dn = t.sort_values("net", ascending=False).head(8), t.sort_values("net").head(8)
    for lab, df in (("증가", ind_up), ("감소", ind_dn)):
        for code, r in df.iterrows():
            L.append(f"| {lab} | {labels.get(code, code)} ({code}) | {r['net']:+,.0f} | {fmt(r['pct'],'pct')} | {r['n']:,.0f} |")
    J["industry_up"] = [{"code": c, "name": labels.get(c, c), "net": int(r["net"]), "pct": float(r["pct"])} for c, r in ind_up.iterrows()]
    J["industry_down"] = [{"code": c, "name": labels.get(c, c), "net": int(r["net"]), "pct": float(r["pct"])} for c, r in ind_dn.iterrows()]
    okp = okg & (S[prev] >= 10) & (S[ym] >= 10) & E[prev].notna() & E[ym].notna() & (C[prev] < 0.9) & (C[ym] < 0.9)
    pm = pd.DataFrame({"prev": E[prev][okp].groupby(grp[okp]).median(), "cur": E[ym][okp].groupby(grp[okp]).median(), "n": okp[okp].groupby(grp[okp]).size()})
    pm = pm[pm["n"] >= 100]
    pm["chg"] = pm["cur"] / pm["prev"] - 1
    L += ["", "## 6. 산업별 추정급여 분포 변화 (전월 대비 중앙값, 상한 비접근·가입자 10명 이상 같은 사업장, 표본 100곳 이상)", "", "| 업종 | 사업장 | 전월 중앙값 | 이번 달 중앙값 | 변화 |", "|---|---|---|---|---|"]
    for code, r in pd.concat([pm.sort_values("chg", ascending=False).head(5), pm.sort_values("chg").head(5)]).iterrows():
        L.append(f"| {labels.get(code, code)} ({code}) | {r['n']:,.0f} | {r['prev']:,.0f} | {r['cur']:,.0f} | {fmt(r['chg'],'pct')} |")
    J["industry_pay_median"] = [{"code": c, "name": labels.get(c, c), "n": int(r["n"]), "chg": float(r["chg"])} for c, r in pm.sort_values("chg", ascending=False).iterrows()][:30]
    fl = cur["flags"].fillna("").str.split("|").explode()
    fl = fl[fl != ""].value_counts()
    cap_t, cap_p = d["cap_ratio"].notna().sum(), None
    L += ["", "## 7. 데이터 이상치·품질 경고", "", "| 경고 | 건수 |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in fl.items()]
    L += ["", f"- 12개월 내 급변(restructure_suspect) 사업장: {int(d['restructure_suspect'].sum()):,}곳 / 현장 단위 사업장(분리): {int(d['project_site'].sum()):,}곳",
          "- 상한액이 바뀐 달(2026-07)을 지나는 비교는 상한 접근 사업장의 급여 변화율을 비웠다(상한 인상 효과 배제).", ""]
    J["flags"] = {k: int(v) for k, v in fl.items()}
    out = ROOT / f"reports/monthly/{ym}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    (ROOT / f"reports/monthly/{ym}.json").write_text(json.dumps(J, ensure_ascii=False, indent=1), encoding="utf-8")


def write_site(P, ms, shift_tab, disp_tab, labels, cands, status, ym):
    """공개용: 산업 단위 집계(개별 기업 없음) + published 콘텐츠."""
    S = P["subs"]
    series = [{"ym": m, "workplaces": int((S[m] >= 3).sum()), "subscribers": int(S[m].fillna(0)[S[m] >= 3].sum())} for m in ms]
    def shape(tab, key):
        return [{"code": c, "name": labels.get(c, c), "base": int(x["base"]), "current": int(x["cur"]), "net": int(x["net"]), "pct": round(float(x["pct"]), 4), "n": int(x["n"])}
                for c, x in tab.sort_values("net", ascending=(key == "decrease")).head(10).iterrows()]
    disp = []
    if len(disp_tab):
        disp = [{"code": x["code"], "name": labels.get(x["code"], x["code"]), "n": int(x["n"]), "ratio_start": round(float(x["ratio0"]), 3), "ratio_end": round(float(x["ratio_t"]), 3),
                 "change": round(float(x["change"]), 4)} for _, x in disp_tab.sort_values("change", ascending=False).head(10).iterrows()]
    out = ROOT / "site/data/insights"
    out.mkdir(parents=True, exist_ok=True)
    trends = {"base_month": ym, "months": ms, "series": series, "industry_increase": shape(shift_tab, "increase"), "industry_decrease": shape(shift_tab, "decrease"),
              "dispersion": disp, "dispersion_threshold": 0.10, "dispersion_groups": int(len(disp_tab)),
              "dispersion_max_change": (round(float(disp_tab["change"].max()), 4) if len(disp_tab) else None), "notes": ["같은 사업장 집합(두 시점 모두 존재) 기준이며 신규·소멸 사업장은 제외된다.", "연봉 양극화는 상한 접근(cap≥0.9) 사업장을 제외한 추정치라 실제 격차보다 작게 나올 수 있다.",
                                              "자동 집계이며 개별 기업에 대한 평가가 아니다."],
              "disclaimer": "국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다."}
    (out / "trends.json").write_text(json.dumps(trends, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pub = I.build_published(cands, status, ROOT / "content/insights")
    (out / "published.json").write_text(json.dumps(pub, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
