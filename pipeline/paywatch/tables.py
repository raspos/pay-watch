"""보험료율·상한액 테이블. 값은 config/*.csv 에서만 읽고 코드에 하드코딩하지 않는다."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class TableError(ValueError):
    pass


def _load(path: Path, value_cols: list[str]) -> pd.DataFrame:
    t = pd.read_csv(path, dtype=str).fillna("")
    for c in ("effective_from", "effective_to"):
        if not t[c].str.fullmatch(r"\d{4}-\d{2}").all():
            raise TableError(f"{path.name}: {c} 는 YYYY-MM 형식이어야 합니다")
    for c in value_cols:
        t[c] = pd.to_numeric(t[c].replace("", None), errors="coerce")
    t = t.sort_values("effective_from").reset_index(drop=True)
    # 기간 겹침 금지 (문자열 YYYY-MM 은 사전순 = 시간순)
    for i in range(1, len(t)):
        if t.loc[i, "effective_from"] <= t.loc[i - 1, "effective_to"]:
            raise TableError(f"{path.name}: 적용기간이 겹칩니다 ({t.loc[i - 1, 'effective_from']}~)")
    return t


def load_rates(path: Path | None = None) -> pd.DataFrame:
    return _load(path or CONFIG_DIR / "nps_rates.csv", ["total_rate", "employee_rate", "employer_rate"])


def load_caps(path: Path | None = None) -> pd.DataFrame:
    return _load(path or CONFIG_DIR / "nps_caps.csv", ["upper_cap", "lower_cap"])


def lookup(table: pd.DataFrame, ym: str, col: str):
    """ym(YYYY-MM)에 적용되는 값. 해당 기간이 없으면 None (임의 예측 금지)."""
    hit = table[(table["effective_from"] <= ym) & (ym <= table["effective_to"])]
    if hit.empty:
        return None
    return float(hit.iloc[0][col])
