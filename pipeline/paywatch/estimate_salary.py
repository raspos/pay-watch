"""국민연금 고지액 기반 연환산 추정. 결과는 '기준소득월액 연환산'이며 실제 연봉이 아니다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .tables import load_caps, load_rates, lookup

PAY_PUBLIC_MIN = 10
CAP_NEAR_RATIO = 0.9
VERY_LOW_MONTHLY = 300_000  # 이 미만이면 이상값 경고(삭제하지 않음)


def estimate(df: pd.DataFrame, rates: pd.DataFrame | None = None, caps: pd.DataFrame | None = None) -> pd.DataFrame:
    rates = load_rates() if rates is None else rates
    caps = load_caps() if caps is None else caps
    out = df.copy()

    yms = out["ym"].unique()
    rate_map = {m: lookup(rates, m, "total_rate") for m in yms}
    cap_map = {m: lookup(caps, m, "upper_cap") for m in yms}
    out["rate"] = out["ym"].map(rate_map).astype(float)
    out["cap"] = out["ym"].map(cap_map).astype(float)

    n = out["subscribers"].astype(float)
    bill = out["bill_amount"].astype(float)
    valid = (n > 0) & (bill > 0) & out["rate"].notna()
    monthly = pd.Series(np.nan, index=out.index)
    monthly[valid] = bill[valid] / n[valid] / out.loc[valid, "rate"]
    out["est_monthly_income"] = monthly
    out["est_annual"] = monthly * 12  # 미검증 추정: 연환산이며 실제 지급 급여가 아님
    out["cap_ratio"] = out["est_monthly_income"] / out["cap"]
    out["cap_flag"] = out["cap_ratio"] >= CAP_NEAR_RATIO

    flags = pd.Series("", index=out.index)

    def add(mask, tag):
        nonlocal flags
        flags = flags.where(~mask, flags + tag + "|")

    add(n <= 0, "no_subscribers")
    add((n > 0) & (bill == 0), "zero_bill")
    add(bill < 0, "negative_bill")
    add(out["rate"].isna(), "no_rate_for_month")
    add(out["cap"].isna() & valid, "no_cap_for_month")
    add(out["status"] == "2", "withdrawn")
    add(out["cap_flag"].fillna(False), "cap_near")
    add(out["cap_ratio"] > 1.01, "above_cap_anomaly")  # 상한 초과: 소급고지·집계범위 차이 의심
    add(out["est_monthly_income"] < VERY_LOW_MONTHLY, "very_low_estimate")
    add(out["subscribers"].between(1, PAY_PUBLIC_MIN - 1), "below_public_threshold")
    add(out.get("dup_key_flag", pd.Series(False, index=out.index)).fillna(False), "dup_key")
    out["flags"] = flags.str.rstrip("|")

    # 공개 가능 여부: 10명 이상 + 계산 가능 + 등록 상태. 3~9명은 검색만 가능.
    out["pay_public"] = valid & (out["subscribers"] >= PAY_PUBLIC_MIN) & (out["status"] == "1")
    out["search_visible"] = (out["subscribers"] >= 3) & (out["status"] == "1")
    out["grade"] = grade(out)
    return out


def grade(df: pd.DataFrame) -> pd.Series:
    """Stage 1 품질 등급. A(공시 확인)는 DART 연동 전이므로 부여하지 않는다.
    D: 비교 부적합(10명 미만·계산 불가·탈퇴·상한 초과 이상), C: 해석 주의(상한 접근·이상 낮음), B: 큰 이상 신호 없음."""
    f = df["flags"]
    d = (
        f.str.contains("no_subscribers|zero_bill|negative_bill|no_rate|no_cap|withdrawn|above_cap_anomaly|below_public_threshold")
        | df["est_annual"].isna()
    )
    c = f.str.contains("cap_near|very_low_estimate|dup_key")
    return pd.Series(np.where(d, "D", np.where(c, "C", "B")), index=df.index)
