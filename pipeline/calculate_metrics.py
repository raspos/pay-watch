"""Stage 3: 13개월 NPS 패널 → 사업장 지표·비교집단·배지·업종/지역 통계·신의 직장 지수 검토. DART 불필요."""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.metrics import (MIN_PEER, SIZE_LABELS, UNCLASSIFIED, add_loss_peer_flag, badges, is_project_site,  # noqa: E402
                              load_panel, peer_table, size_bucket, workplace_metrics)

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data/interim"
BADGE_KO = {"cap_caution": "급여 상한 주의", "pay_high_in_industry": "업종 내 고연봉", "headcount_up": "가입자 증가",
            "headcount_down": "가입자 감소", "loss_rate_high": "상실률 높음", "restructure_check": "사업장 변동 확인 필요"}
BENCH = {"삼성전자": ["삼성전자"], "SK하이닉스": ["에스케이하이닉스"], "현대자동차": ["현대자동차"], "기아": ["기아"],
         "네이버": ["네이버"], "카카오": ["카카오"], "KB국민은행": ["국민은행"], "신한은행": ["신한은행"],
         "포스코": ["포스코"], "LG전자": ["엘지전자"]}


def won(x):
    return "—" if pd.isna(x) else f"{x:,.0f}"


def pct(x, d=1):
    return "—" if pd.isna(x) else f"{x*100:.{d}f}%"


def main():
    ms = sorted(p.split("nps_")[1][:7] for p in glob.glob(str(INTERIM / "nps_20*.parquet")))
    assert len(ms) == 13, ms
    t = ms[-1]
    P = load_panel(INTERIM, ms)
    wm = workplace_metrics(P, ms)

    cur = pd.read_parquet(INTERIM / f"nps_{t}.parquet", columns=[
        "name_raw", "name_norm", "industry_code", "industry_name", "sido", "sigungu", "addr_jibun", "subscribers", "est_annual",
        "cap_ratio", "cap_flag", "pay_public", "search_visible", "grade", "flags", "status", "type_code"])
    cur.index = pd.read_parquet(INTERIM / f"ids_{t}.parquet")["wp_id"].values
    d = cur.join(wm.drop(columns=["subs"]), how="left").rename(columns={"subscribers": "subs"})
    d["subs"] = cur["subscribers"]
    d["project_site"] = is_project_site(d["name_raw"])
    d = peer_table(d)
    tops = d.attrs.get("group_tops", {})                    # 비교집단별 상위 목록(상한 비접근) → "더 잘 주는 곳" 화면용
    gids = {k: i for i, k in enumerate(sorted(tops))}      # 집단 키 → 정수 번호(정렬 순서라 입력이 같으면 번호도 같다)
    d["peer_gid"] = d["peer_gkey"].map(gids).astype("Int64")
    (INTERIM / f"peer_groups_{t}.json").write_text(json.dumps({"groups": {str(gids[k]): v for k, v in tops.items()}}, ensure_ascii=False), encoding="utf-8")
    d = add_loss_peer_flag(d)
    d["badges"] = badges(d)
    d["history_complete"] = d["months_present"] == len(ms)
    d.to_parquet(INTERIM / f"metrics_{t}.parquet")

    pub = d[d.pay_public]
    ps = pub[pub.project_site]
    L_site = ["## 0. 건설 현장 단위 사업장(회사 아님) 분리", "",
              f"- 이름 패턴(`/일용/`, `/상용/`, `건설일용`)으로 식별: 검색 대상 {int(d[d.search_visible].project_site.sum()):,}곳 / 연봉 공개 대상 {len(ps):,}곳({pct(len(ps)/len(pub))})",
              f"- 이 사업장들의 추정급여 중앙값 {won(ps.est_annual.median())}원 vs 나머지 {won(pub[~pub.project_site].est_annual.median())}원 → 섞으면 건설업 비교집단·순위가 왜곡됨",
              "- 조치: 비교집단·순위·지수 검토에서 제외, 상세 화면에 ‘현장 단위 사업장’ 안내(검색은 가능)", ""]
    L = [f"# Stage 3 지표 리포트 — 기준월 {t} (NPS 13개월 {ms[0]}~{ms[-1]}, DART 미사용)", "",
         "※ 아래 모든 수치는 국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다. DART 공시 값은 사용하지 않았습니다.", ""]

    # 1. 지표별 계산 가능 범위
    L += ["## 1. 지표별 계산 가능 사업장 (연봉 공개 대상 %s곳 기준)" % f"{len(pub):,}", "", "| 지표 | 계산됨 | 비율 |", "|---|---|---|"]
    for c, name in [("peer_median", "비교집단 지표(업종×규모, 부족하면 인접 규모 구간과 병합, 표본≥30)"), ("pay_pct", "급여 백분위"),
                    ("growth_12m", "12개월 가입자 증감률"), ("lost_cum_12m", "12개월 누적 상실률"),
                    ("pay_change_12m", "12개월 추정급여 변화율(상한 영향 배제)"), ("growth_3m", "3개월 가입자 증감률")]:
        n = int(pub[c].notna().sum())
        L.append(f"| {name} | {n:,} | {pct(n/len(pub))} |")
    L += ["", f"- 업종코드 미분류(999999 등) 공개 대상: {int(pub.industry_code.isin(UNCLASSIFIED).sum()):,}곳 → 업종 비교 불가",
          f"- 비교집단 범위: {pub.peer_scope.value_counts(dropna=False).to_dict()}",
          f"- 13개월 내내 존재(history_complete): {int(pub.history_complete.sum()):,}곳 ({pct(pub.history_complete.mean())})",
          f"- 12개월 내 급변(restructure_suspect): {int(pub.restructure_suspect.sum()):,}곳", ""]
    L += ["## 2. 추정급여 변화율: 상한 효과를 배제하지 않으면 생기는 왜곡", "",
          "2026-07 상한 인상(637→659만원)의 영향을 확인하기 위해 같은 사업장의 12개월 전 대비 변화율을 두 방식으로 비교했다.", ""]
    e_t, e_b = P["est_m"][t], P["est_m"][ms[0]]
    both = e_t.notna() & e_b.notna() & P["subs"][t].ge(10) & P["subs"][ms[0]].ge(10)
    naive = (e_t / e_b - 1)[both]
    cap_now = P["cap"][t].reindex(naive.index) >= 0.9
    L += ["| 구분 | 사업장 | 중앙값 | 비고 |", "|---|---|---|---|",
          f"| 전체(단순 계산) | {len(naive):,} | {pct(naive.median(),2)} | |",
          f"| 상한 접근(≥0.9)인 사업장 | {int(cap_now.sum()):,} | {pct(naive[cap_now].median(),2)} | 상한 인상(+3.5%) 효과가 섞임 |",
          f"| 상한 비접근 사업장 | {int((~cap_now).sum()):,} | {pct(naive[~cap_now].median(),2)} | |",
          f"| **본 지표(양쪽 달 상한 비접근만)** | {int(pub.pay_change_12m.notna().sum()):,} | {pct(pub.pay_change_12m.median(),2)} | 공개용 정의 |", "",
          f"- 상한 인상률 자체: {6_590_000/6_370_000-1:.2%}. 상한 접근 사업장은 단순 변화율이 상한 인상 효과로 부풀 수 있어(중앙값 차이 위 표 참고) 변화율을 비운다.",
          "- 상한에 걸리지 않은 사업장도 일부 직원이 절단됐을 수 있어 '추정급여 변화율'은 실제 임금 인상률이 아니다.", ""]

    # 3. 비교집단 구조
    L += ["## 3. 비교집단(업종을 가장 세분한 것부터: 6자리 → 4자리 → 2자리 코드, 각 단계에서 같은 규모 → 인접 규모 병합)", ""]
    sc = pub.peer_scope.value_counts()
    L += ["| 비교집단 단계 | 사업장 | 비율 |", "|---|---|---|"] + [f"| {k} | {v:,} | {pct(v/len(pub))} |" for k, v in sc.items()]
    L += ["", f"- 비교 불가(업종 미분류 또는 표본 30곳 미만): {int(pub.peer_scope.isna().sum()):,}곳 ({pct(pub.peer_scope.isna().mean())})",
          f"- 사용된 비교집단의 평균 업종 구성 수: 6자리 단계는 단일 업종, 4자리·2자리 단계는 '외 N개 업종'으로 화면에 표시",
          f"- 규모별 비교 가능 비율: " + ", ".join(f"{k} {pct(v)}" for k, v in pub.groupby('size_bucket', observed=True).peer_median.apply(lambda s: s.notna().mean()).items()), ""]
    ind = pub[pub.peer_scope.notna()].groupby("ind2").agg(업종=("industry_name", lambda s: s.mode().iat[0]), 사업장=("subs", "size"),
                                                         가입자=("subs", "sum"), 중앙값=("est_annual", "median"),
                                                         상한접근=("cap_flag", "mean"), 성장중앙=("growth_12m", "median"),
                                                         상실중앙=("lost_cum_12m", "median"))
    ind = ind[ind.사업장 >= MIN_PEER].sort_values("가입자", ascending=False)
    L += ["### 업종 코드 앞 2자리 그룹 통계 (가입자 상위 15, 표본≥30; 그룹명은 최다 업종의 이름이며 그룹 안에 여러 업종이 섞여 있음)", "", "| 업종 | 사업장 | 가입자 | 추정급여 중앙값 | 상한접근 | 12개월 증감 중앙 | 12개월 누적 상실 중앙 |", "|---|---|---|---|---|---|---|"]
    for k, r in ind.head(15).iterrows():
        L.append(f"| {k} {r.업종} | {int(r.사업장):,} | {int(r.가입자):,} | {won(r.중앙값)} | {pct(r.상한접근)} | {pct(r.성장중앙)} | {pct(r.상실중앙)} |")
    ind.to_csv(INTERIM / f"industry_stats_{t}.csv", encoding="utf-8-sig")
    reg = pub.groupby("sido").agg(사업장=("subs", "size"), 중앙값=("est_annual", "median"), 상한접근=("cap_flag", "mean"))
    reg = reg[reg.사업장 >= MIN_PEER].sort_values("중앙값", ascending=False)
    L += ["", "### 시도별 통계 (코드 기준, 표본≥30)", "", "| 시도코드 | 사업장 | 추정급여 중앙값 | 상한접근 |", "|---|---|---|---|"]
    for k, r in reg.iterrows():
        L.append(f"| {k} | {int(r.사업장):,} | {won(r.중앙값)} | {pct(r.상한접근)} |")
    reg.to_csv(INTERIM / f"region_stats_{t}.csv", encoding="utf-8-sig")

    # 4. 배지
    L += ["", "## 4. 배지 (중립 표현, 공개 대상 기준)", "", "| 배지 | 사업장 |", "|---|---|"]
    bs = pub.badges.str.split(",").explode()
    for k, v in bs[bs != ""].value_counts().items():
        L.append(f"| {BADGE_KO.get(k, k)} | {v:,} |")
    L += ["", "- 가입자 증감·상실률 배지는 `restructure_suspect` 사업장에서는 붙지 않는다. '탈출' 등 강한 표현은 쓰지 않는다.", ""]

    # 5. 10개 기업
    L += ["## 5. 주요 10개 기업 (이름이 완전히 일치하는 사업장, 합산 아님)", "",
          "| 사업장 | 가입자 | 12개월 증감 | 12개월 누적 상실 | 급여 백분위 | 비교집단 | 프리미엄 | 변화율 | 배지 | 등급 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for lab, names in BENCH.items():
        r = d[(d.name_norm.isin([x.upper() for x in names])) & (d.status == "1")].sort_values("subs", ascending=False).head(1)
        if r.empty:
            L.append(f"| {lab} | 미확인 | | | | | | | | |")
            continue
        r = r.iloc[0]
        cen = "(상한 절단: 하한값)" if r.pay_censored else ""
        L.append(f"| {r['name_raw']} | {int(r.subs):,} | {pct(r.growth_12m)} | {pct(r.lost_cum_12m)} | {pct(r.pay_pct,0)}{cen} | " +
                 (f"{r.peer_label}·{r.size_bucket}({int(r.peer_n)}곳, {r.peer_scope}) | " if pd.notna(r.peer_n) else "비교 불가(표본 30곳 미만) | ") +
                 f"{pct(r.pay_premium)} | {pct(r.pay_change_12m)} ({r.pay_change_reason}) | {', '.join(BADGE_KO.get(b, b) for b in r.badges.split(',') if b) or '—'} | {r.grade} |")
    L[4:4] = L_site
    open(ROOT / f"reports/quality/stage3_metrics_{t}.md", "w", encoding="utf-8").write("\n".join(L))

    god_review(d, t)
    print("ok", len(d), int(d.pay_public.sum()))


def god_review(d, t):
    w = yaml.safe_load(open(ROOT / "config/god_job_weights.yaml", encoding="utf-8"))
    comp = w["components"]
    use = w["basic_index"]["use"]
    pub = d[d.pay_public & ~d.project_site].copy()
    ind_ok = ~pub.industry_code.isin(UNCLASSIFIED) & (pub.ind2 != "00")   # 업종 4자리 × 규모 안에서만 백분위

    def pct_in_ind(col, invert=False):
        s = pub[col].where(ind_ok)
        key = [pub["ind4"], pub["size_bucket"]]            # 업종 4자리 × 규모 안에서만 순위(이질적 업종·규모 혼합 방지)
        n = s.groupby(key, observed=True).transform("count")
        r = s.groupby(key, observed=True).rank(pct=True)
        r = r.where(n >= MIN_PEER)
        return 1 - r if invert else r

    pub["s_pay"] = pub["pay_pct"]
    pub["s_stab"] = pct_in_ind("lost_cum_12m", invert=True)
    pub["s_growth"] = pct_in_ind("growth_12m")
    pub["s_tenure"] = np.nan                                              # DART 미확보 → unavailable
    sc = {"pay_competitiveness": "s_pay", "employment_stability": "s_stab", "growth": "s_growth", "tenure": "s_tenure"}
    wsum = sum(comp[k] for k in use)
    pub["basic"] = sum(comp[k] * pub[sc[k]] for k in use) / wsum * 100
    elig = (pub[[sc[k] for k in use]].notna().all(axis=1) & pub.history_complete & ~pub.restructure_suspect.fillna(False))
    e = pub[elig]
    e_rank = e[~e.pay_censored.fillna(False)]

    L = [f"# 신의 직장 지수 검토 — {t} (공개 보류)", "",
         "가중치(`config/god_job_weights.yaml`)는 잠정안이다. 이 문서는 어떤 방식이 공정·해석 가능한지 데이터로 비교한 검토 결과이며, **종합 순위는 공개하지 않는다.**", "",
         "## 방식별 산출 가능 범위", "", "| 방식 | 산출 가능 사업장 | 공개 대상 대비 |", "|---|---|---|",
         f"| A. 4개 항목(근속 포함) 모두 있는 기업만 | 0 | 0.0% (DART 근속 미확보 → 현재 불가) |",
         f"| B. 공통 데이터 기본지수(근속 제외, 가중치 재정규화 {wsum:.2f}) | {len(e):,} | {len(e)/len(pub)*100:.1f}% |",
         f"| B'. 기본지수 중 상한 절단 기업 제외 | {len(e_rank):,} | {len(e_rank)/len(pub)*100:.1f}% |",
         f"| C. 항목별 점수만 공개 | 항목별로 각각 | 급여백분위 {pub.s_pay.notna().mean()*100:.1f}% · 안정성 {pub.s_stab.notna().mean()*100:.1f}% · 증가 {pub.s_growth.notna().mean()*100:.1f}% |", ""]
    # 왜곡 진단
    top = e.nlargest(max(1, len(e) // 100), "basic")
    L += ["## 왜곡 진단 (기본지수 B 기준)", "",
          f"- 상위 1%({len(top):,}곳) 중 급여가 상한에 걸린 사업장 비율: {pct(top.cap_flag.mean())} (전체 eligible: {pct(e.cap_flag.mean())})",
          f"- 상한에 걸린 사업장은 급여 백분위가 '실제 이상'일 수 있어 순위가 맞는지 검증할 수 없다(절단). 전체 eligible 중 {pct(e.pay_censored.mean())}.",
          f"- 지수와 가입자 수(규모)의 스피어만 상관: {e['basic'].corr(e['subs'], method='spearman'):.3f}",
          f"- 항목 간 상관(스피어만): 급여–안정성 {e.s_pay.corr(e.s_stab, method='spearman'):.3f}, 급여–증가 {e.s_pay.corr(e.s_growth, method='spearman'):.3f}, 안정성–증가 {e.s_stab.corr(e.s_growth, method='spearman'):.3f}",
          f"- 안정성 항목은 12개월 누적 상실률(납부예외 포함)을 쓰므로 '퇴사율이 낮다'로 해석할 수 없고, 가입자 수와의 상관 {e.s_stab.corr(e['subs'], method='spearman'):.3f}", ""]
    gaps = e.groupby("size_bucket", observed=True).agg(n=("basic", "size"), 중앙=("basic", "median"), 상한=("cap_flag", "mean"))
    L += ["### 규모별 기본지수", "", "| 규모 | 사업장 | 지수 중앙값 | 상한 절단 |", "|---|---|---|---|"]
    for k, r in gaps.iterrows():
        L.append(f"| {k} | {int(r.n):,} | {r.중앙:.1f} | {pct(r.상한)} |")
    L += ["", "## 권고", "",
          "1. **종합 순위는 공개하지 않는다.** 대기업 구간에서 급여 항목이 상한 절단으로 변별력을 잃고(위 표), 근속은 DART 확보 전에는 없다.",
          "2. **B(공통 데이터 기본지수)와 C(항목별 점수)를 병행**한다. A는 비상장 대부분이 탈락해 공정하지 않고, 결측을 0점 처리하는 방식은 채택하지 않는다.",
          "3. 지수 대신 상한 비접근 사업장에 한해 업종 내 백분위·프리미엄·증감을 항목별로 보여주고, 종합 점수는 신뢰도(데이터 충족률)와 함께 내부 검토용으로만 둔다.",
          "4. 공개 전 필요: (a) DART로 근속과 공시 급여 확보, (b) 상한 보정 가능성의 검증, (c) 가중치의 민감도 분석."]
    open(ROOT / f"reports/quality/god_job_index_review_{t}.md", "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
