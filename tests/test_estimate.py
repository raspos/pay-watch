"""합성 데이터만 사용하는 단위 테스트(실제 CSV 불필요)."""
import pandas as pd
import pytest

from paywatch.estimate_salary import estimate
from paywatch.load_nps import assert_no_month_overlap, clean
from paywatch.tables import TableError, _load, load_caps, load_rates, lookup


def row(ym="2026-09", n=100, bill=0, status="1", name="테스트(주)", brn="123456", applied="2000-01-01", **kw):
    d = dict(ym=ym, name=name, brn6=brn, status=status, zip="1", addr_jibun="a", addr_road="b",
             legal_dong="1", admin_dong="1", sido="11", sigungu="110", emd="101", type_code="1",
             industry_code="1", industry_name="x", applied_date=applied, rereg_date=None,
             withdrawn_date=None, subscribers=str(n), bill_amount=str(bill), acquired="0", lost="0")
    d.update(kw)
    return d


def est(rows):
    df, _ = clean(pd.DataFrame(rows))
    return estimate(df)


# ---- 보험료율 경계 ----
@pytest.mark.parametrize("ym,rate", [("2025-12", 0.09), ("2026-01", 0.095), ("2026-12", 0.095), ("2027-01", 0.10), ("2033-01", 0.13)])
def test_rate_boundaries(ym, rate):
    assert lookup(load_rates(), ym, "total_rate") == pytest.approx(rate)


def test_rate_applied_in_estimate():
    # 100명, 월 기준소득 300만원 → 고지액 = 100*3,000,000*rate
    for ym, rate in [("2025-12", 0.09), ("2026-01", 0.095), ("2027-01", 0.10)]:
        out = est([row(ym=ym, n=100, bill=round(100 * 3_000_000 * rate))])
        assert out.loc[0, "est_monthly_income"] == pytest.approx(3_000_000, rel=1e-6)
        assert out.loc[0, "est_annual"] == pytest.approx(36_000_000, rel=1e-6)


# ---- 상한 경계 ----
def test_cap_june_2026():
    assert lookup(load_caps(), "2026-06", "upper_cap") == 6_370_000


def test_cap_july_2026():
    assert lookup(load_caps(), "2026-07", "upper_cap") == 6_590_000


def test_no_future_cap_guess():
    assert lookup(load_caps(), "2027-07", "upper_cap") is None
    out = est([row(ym="2027-07", n=10, bill=10_000_000)])
    assert pd.isna(out.loc[0, "cap_ratio"]) and "no_cap_for_month" in out.loc[0, "flags"]


def test_rate_table_overlap_rejected(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("effective_from,effective_to,total_rate\n2025-01,2025-12,0.09\n2025-12,2026-12,0.095\n", encoding="utf-8")
    with pytest.raises(TableError):
        _load(p, ["total_rate"])


# ---- 비정상 입력 ----
def test_zero_subscribers_is_null():
    out = est([row(n=0, bill=1_000_000)])
    assert pd.isna(out.loc[0, "est_annual"]) and out.loc[0, "grade"] == "D"
    assert "no_subscribers" in out.loc[0, "flags"] and not out.loc[0, "pay_public"]


def test_missing_bill_is_null_not_zero():
    out = est([row(n=50, bill=None)])  # 고지금액 누락 → 격리
    assert out.empty


def test_zero_bill_not_zero_salary():
    out = est([row(n=50, bill=0)])
    assert pd.isna(out.loc[0, "est_annual"]) and "zero_bill" in out.loc[0, "flags"]


def test_negative_bill_not_published():
    out = est([row(n=50, bill=-5_000_000)])
    assert pd.isna(out.loc[0, "est_annual"]) and out.loc[0, "grade"] == "D"


def test_above_cap_flagged_not_extrapolated():
    # 월 기준소득이 상한(659만)을 10% 넘게 나오는 입력 → 이상 경고, 값은 그대로(외삽·보정 없음)
    bill = round(100 * 7_250_000 * 0.095)
    out = est([row(n=100, bill=bill)])
    assert "above_cap_anomaly" in out.loc[0, "flags"] and out.loc[0, "grade"] == "D"
    assert out.loc[0, "cap_ratio"] > 1.01


def test_cap_near_warning():
    bill = round(100 * 6_200_000 * 0.095)
    out = est([row(n=100, bill=bill)])
    assert bool(out.loc[0, "cap_flag"]) and out.loc[0, "grade"] == "C"


# ---- 공개 정책 ----
def test_public_threshold():
    out = est([row(n=9, bill=9 * 3_000_000 * 0.095, name="a"), row(n=10, bill=10 * 3_000_000 * 0.095, name="b"),
               row(n=2, bill=2 * 3_000_000 * 0.095, name="c")]).set_index("name_raw")
    assert not out.loc["a", "pay_public"] and out.loc["a", "search_visible"]
    assert out.loc["b", "pay_public"]
    assert not out.loc["c", "search_visible"]


# ---- 중복 ----
def test_exact_duplicate_quarantined_not_deleted():
    df = pd.DataFrame([row(bill=1000), row(bill=1000)])
    ok, q = clean(df)
    assert len(ok) == 1 and len(q) == 1 and q.iloc[0]["reason"] == "exact_duplicate"


def test_same_key_different_values_flagged_not_merged():
    df = pd.DataFrame([row(n=10, bill=1000), row(n=20, bill=2000)])
    ok, q = clean(df)
    assert len(ok) == 2 and ok["dup_key_flag"].all() and q.empty
    assert "dup_key" in estimate(ok)["flags"].iloc[0]


def test_same_name_different_workplaces_not_merged():
    df = pd.DataFrame([row(brn="111111"), row(brn="222222")])
    ok, _ = clean(df)
    assert len(ok) == 2 and not ok["dup_key_flag"].any()


def test_duplicate_month_input_rejected():
    existing = pd.DataFrame({"ym": ["2026-09"]})
    with pytest.raises(ValueError):
        assert_no_month_overlap(existing, ["2026-09"])
    assert_no_month_overlap(existing, ["2026-10"])


def test_invalid_month_quarantined():
    ok, q = clean(pd.DataFrame([row(ym="2026-13"), row(ym="2026-09", name="ok")]))
    assert len(ok) == 1 and "invalid_ym" in q.iloc[0]["reason"]
