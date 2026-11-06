import numpy as np
import pandas as pd
import pytest

from paywatch.metrics import MIN_PEER, add_loss_peer_flag, badges, is_project_site, peer_table, workplace_metrics

MS = [f"2025-{m:02d}" for m in range(9, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]  # 13개월


def panel(rows, months=MS):
    """rows: {wp_id: dict(subs=[...13], lost=[...], acq=[...], est=[...], cap=[...])}"""
    idx = list(rows)
    mk = lambda k: pd.DataFrame([rows[i][k] for i in idx], index=idx, columns=months, dtype=float)
    return {"subs": mk("subs"), "lost": mk("lost"), "acq": mk("acq"), "est_m": mk("est"), "cap": mk("cap")}


def flat(v, n=13):
    return [v] * n


def row(subs=100, lost=2, est=3_000_000, cap=0.5):
    s = subs if isinstance(subs, list) else flat(subs)
    return dict(subs=s, lost=flat(lost), acq=flat(1), est=flat(est) if not isinstance(est, list) else est,
                cap=flat(cap) if not isinstance(cap, list) else cap)


def test_growth_12m_and_net():
    P = panel({1: row(subs=[100] * 12 + [115])})
    m = workplace_metrics(P, MS)
    assert m.loc[1, "growth_12m"] == pytest.approx(0.15) and m.loc[1, "net_12m"] == 15


def test_no_12m_metrics_with_fewer_than_13_months():
    ms = MS[-12:]
    r = row()
    r = {k: v[:12] for k, v in r.items()}
    P = panel({1: r}, ms)
    m = workplace_metrics(P, ms)
    assert np.isnan(m.loc[1, "growth_12m"]) and np.isnan(m.loc[1, "lost_cum_12m"]) and m.loc[1, "pay_change_reason"] == "insufficient_history"


def test_cumulative_loss_requires_all_12_months():
    r = row(subs=100, lost=5)
    r["subs"][5] = np.nan                                      # 중간 달 누락
    m = workplace_metrics(panel({1: r, 2: row(subs=100, lost=5)}), MS)
    assert np.isnan(m.loc[1, "lost_cum_12m"])
    assert m.loc[2, "lost_cum_12m"] == pytest.approx(12 * 5 / 100)   # 12개월 합 ÷ 평균 가입자


def test_small_base_not_extrapolated():
    m = workplace_metrics(panel({1: row(subs=[5] * 12 + [50])}), MS)
    assert np.isnan(m.loc[1, "growth_12m"])                    # 기준 시점 5명 → 증감률 미계산


def test_pay_change_excludes_cap_affected():
    # 상한 접근 달이 있으면 변화율을 내지 않는다(상한 인상으로 인한 가짜 상승 방지)
    capped = row(est=[6_000_000] * 12 + [6_300_000], cap=[0.94] * 12 + [0.95])
    free = row(est=[3_000_000] * 12 + [3_150_000], cap=[0.4] * 13)
    m = workplace_metrics(panel({1: capped, 2: free}), MS)
    assert np.isnan(m.loc[1, "pay_change_12m"]) and m.loc[1, "pay_change_reason"] == "cap_affected"
    assert m.loc[2, "pay_change_12m"] == pytest.approx(0.05)


def test_restructure_suspect_flag():
    r = row(subs=[100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 250])
    m = workplace_metrics(panel({1: r, 2: row()}), MS)
    assert bool(m.loc[1, "restructure_suspect"]) and not bool(m.loc[2, "restructure_suspect"])


def test_loss_rate_denominator_is_previous_month():
    r = row(subs=[100] * 12 + [200], lost=10)
    m = workplace_metrics(panel({1: r}), MS)
    assert m.loc[1, "lost_rate_month"] == pytest.approx(10 / 100)  # 당월(200)이 아니라 전월(100)


# ---- 비교집단 ----
def peers(n, est=lambda i: 3e7 + i * 1e5, ind="472100", subs=50, cap=False, pub=True):
    return pd.DataFrame({"industry_code": ind, "industry_name": "업종X", "subs": subs, "est_annual": [est(i) for i in range(n)],
                         "cap_flag": cap, "pay_public": pub, "sido": "11"}, index=range(n))


def test_peer_group_requires_min_sample():
    small = peer_table(peers(MIN_PEER - 1))
    assert small["peer_median"].isna().all() and small["pay_premium"].isna().all()
    big = peer_table(peers(MIN_PEER))
    assert big["peer_scope"].eq("code6_size").all() and big["peer_n"].eq(MIN_PEER).all()


def test_pay_premium_and_percentile():
    d = peer_table(peers(41))
    med = d["est_annual"].median()
    assert d["pay_premium"].iloc[-1] == pytest.approx(d["est_annual"].iloc[-1] / med - 1)
    assert d["pay_pct"].iloc[-1] == pytest.approx(1.0) and d["pay_pct"].iloc[0] == pytest.approx(1 / 41)


def test_unclassified_industry_has_no_peer_stats():
    assert peer_table(peers(40, ind="999999"))["peer_median"].isna().all()


def test_merge_adjacent_size_bucket_when_too_small():
    a = peers(40, subs=50)                                   # 30-99 구간 40곳
    b = peers(20, subs=150)                                  # 100-299 구간 20곳(부족) → 인접 30-99 와 병합 가능
    d = peer_table(pd.concat([a, b], ignore_index=True))
    assert (d.loc[d.subs == 50, "peer_scope"] == "code6_size").all()
    assert (d.loc[d.subs == 150, "peer_scope"] == "code6_merged").all()
    assert d.loc[d.subs == 150, "peer_n"].eq(60).all()


def test_no_industry_wide_fallback_for_distant_sizes():
    a = peers(40, subs=50)
    b = peers(5, subs=5000)                                  # 1000+ 5곳: 인접(300-999)도 없음 → 비교 불가
    d = peer_table(pd.concat([a, b], ignore_index=True))
    assert d.loc[d.subs == 5000, "peer_median"].isna().all() and d.loc[d.subs == 5000, "peer_scope"].isna().all()


def test_non_public_excluded_from_peers():
    d = peer_table(peers(40, pub=False))
    assert d["peer_median"].isna().all()


def test_cap_flag_marks_percentile_censored_and_blocks_pay_badge():
    base = peers(40)
    base.loc[39, "cap_flag"] = True
    d = peer_table(base)
    d["restructure_suspect"] = False
    d["growth_12m"] = np.nan
    d["lost_high"] = False
    d["pay_censored"] = d["pay_censored"].fillna(False)
    b = badges(d)
    assert d.loc[39, "pay_censored"] and "cap_caution" in b[39] and "pay_high_in_industry" not in b[39]
    assert "pay_high_in_industry" in b[38]


def test_badges_neutral_and_suppressed_on_restructure():
    d = pd.DataFrame({"cap_flag": [False], "pay_pct": [0.5], "pay_censored": [False], "growth_12m": [-0.4], "subs": [100],
                      "lost_high": [True], "restructure_suspect": [True]})
    b = badges(d)[0]
    assert "headcount_down" not in b and "loss_rate_high" not in b and "restructure_check" in b
    assert not any(w in b for w in ("exodus", "탈출"))


def test_loss_high_needs_peer_sample():
    d = peers(40)
    d["lost_cum_12m"] = np.linspace(0, 1, 40)
    d = add_loss_peer_flag(d)
    assert d["lost_high"].sum() == 4 and d.loc[39, "lost_high"]
    few = add_loss_peer_flag(peers(10).assign(lost_cum_12m=np.linspace(0, 1, 10)))
    assert not few["lost_high"].any()


def test_finer_industry_code_preferred_over_coarse_group():
    # 같은 2자리(74) 안에서 6자리 코드가 다르면 세분 코드 집단(40곳)끼리 비교하고 이질적 업종과 섞지 않는다
    a = peers(40, ind="741101", est=lambda i: 9e7 + i * 1e5)          # 변호사업형
    b = peers(40, ind="749300", est=lambda i: 2e7 + i * 1e5)          # 청소업형
    d = peer_table(pd.concat([a, b], ignore_index=True))
    assert d["peer_scope"].eq("code6_size").all()
    assert d.iloc[:40]["peer_median"].min() > 8e7 and d.iloc[40:]["peer_median"].max() < 3e7


def test_falls_back_to_coarser_code_and_labels_group():
    # 6자리 코드마다 20곳(부족) → 같은 4자리 아래에서 합쳐 40곳 이상이면 4자리 집단 사용
    parts = [peers(20, ind="742104").assign(industry_name="엔지니어링"), peers(20, ind="742105").assign(industry_name="측량")]
    d = peer_table(pd.concat(parts, ignore_index=True))
    assert d["peer_scope"].eq("code4_size").all() and d["peer_level"].eq(4).all()
    assert d["peer_label"].str.contains("외 1개 업종").all()


def test_project_site_pattern():
    names = pd.Series(["(주)가경/일용/평택 P4 Hook Up", "주식회사 가경/상용/2026년 교통신호시설 공사", "삼성전자(주)", "건설일용 사업장", "일용품 도매(주)"])
    assert is_project_site(names).tolist() == [True, True, False, True, False]


def test_project_sites_excluded_from_peer_groups():
    d = peers(40)
    d["project_site"] = False
    d.loc[:9, "project_site"] = True                         # 10곳은 현장 단위 → 비교집단 표본 30 으로 줄지만 자신은 비교 제외
    out = peer_table(d)
    assert out.loc[:9, "peer_median"].isna().all() and out.loc[10:, "peer_n"].eq(30).all()
