"""모든 월 interim parquet 에 wp_id 를 붙여 data/interim/ids_{ym}.parquet 로 저장하고 연결 통계를 출력."""
import glob
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.workplace_ids import assign_month  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COLS = ["ym", "name_raw", "name_norm", "brn6", "applied_date", "legal_dong", "sigungu", "status", "dup_key_flag"]


def main():
    files = sorted(glob.glob(str(ROOT / "data/interim/nps_20*.parquet")))
    prev, next_id, rows = None, 1, []
    for f in files:
        cur = pd.read_parquet(f, columns=COLS).reset_index(drop=True)
        ym = cur["ym"].iloc[0]
        cur, next_id = assign_month(cur, prev, next_id)
        cur[["wp_id", "link_tier"]].to_parquet(ROOT / f"data/interim/ids_{ym}.parquet")
        tiers = cur["link_tier"].value_counts().to_dict()
        rows.append({"ym": ym, "rows": len(cur), **tiers})
        print(ym, len(cur), tiers, flush=True)
        prev = cur
    pd.DataFrame(rows).fillna(0).to_csv(ROOT / "reports/quality/wp_id_linking.csv", index=False)


if __name__ == "__main__":
    main()
