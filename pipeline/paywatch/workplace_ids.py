"""월별 사업장에 안정적인 wp_id 를 '발급'한다(계산이 아니라 원장 기반).
직전 월과 단계별 규칙으로 1:1 로 확실히 대응되는 경우에만 같은 ID 를 잇고, 모호하면 새 ID 를 발급한다."""
from __future__ import annotations

import pandas as pd

# (단계 이름, 키 컬럼). 앞 단계일수록 엄격.
TIERS = [
    ("t1_name_brn_applied_dong", ["name_norm", "brn6", "applied_date", "legal_dong"]),
    ("t2_brn_applied_sigungu", ["brn6", "applied_date", "sigungu"]),       # 상호 변경
    ("t3_name_brn_dong", ["name_norm", "brn6", "legal_dong"]),             # 재등록(적용일자 변경)
    ("t4_name_brn_applied", ["name_norm", "brn6", "applied_date"]),        # 이전(주소 변경)
]


def _link(prev: pd.DataFrame, cur: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """남은 행끼리 cols 가 같고 양쪽 모두 유일한 경우만 (cur_idx, wp_id) 반환."""
    p = prev[~prev.duplicated(cols, keep=False)]
    c = cur[~cur.duplicated(cols, keep=False)]
    m = c.drop(columns=["wp_id"], errors="ignore").reset_index().merge(p[cols + ["wp_id"]], on=cols, how="inner")
    m = m.drop_duplicates("wp_id", keep=False)  # 하나의 이전 ID 에 둘 이상 대응하면 연결 안 함
    return m.set_index("index")[["wp_id"]]


def assign_month(cur: pd.DataFrame, prev: pd.DataFrame | None, next_id: int) -> tuple[pd.DataFrame, int]:
    """cur: 해당 월 정제본(인덱스는 월 안에서 고유). prev: 직전 월 (wp_id 포함)."""
    cur = cur.copy()
    cur["wp_id"] = pd.NA
    cur["link_tier"] = ""
    if prev is not None:
        for name, cols in TIERS:
            free_c = cur[cur["wp_id"].isna()]
            used = set(cur["wp_id"].dropna())
            free_p = prev[~prev["wp_id"].isin(used)]
            hit = _link(free_p, free_c, cols)
            if hit.empty:
                continue
            cur.loc[hit.index, "wp_id"] = hit["wp_id"]
            cur.loc[hit.index, "link_tier"] = name
    new = cur["wp_id"].isna()
    n = int(new.sum())
    cur.loc[new, "wp_id"] = range(next_id, next_id + n)
    cur.loc[new, "link_tier"] = "new" if prev is not None else "init"
    cur["wp_id"] = cur["wp_id"].astype("int64")
    return cur, next_id + n
