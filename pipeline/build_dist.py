"""홈 화면 분포 그래프용 집계 → site/data/dist.json. 개별 기업이 아닌 전체 분포(공개 대상 사업장, 현장 단위 제외)."""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.export_public import write_json  # noqa: E402
from paywatch.tables import load_caps, lookup  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LO, HI, STEP = 10_000_000, 80_000_000, 2_500_000


def histogram(est: pd.Series):
    """edges: LO..HI(STEP). counts: [LO 미만, 구간..., HI 이상]. 합계는 표본 수와 같다."""
    edges = list(range(LO, HI + 1, STEP))
    inner, _ = np.histogram(est[(est >= LO) & (est < HI)], bins=edges)   # 마지막 구간이 오른쪽 끝을 포함하므로 범위 안의 값만 넣는다(HI 이상은 별도 구간)
    return edges, [int((est < LO).sum()), *[int(x) for x in inner], int((est >= HI).sum())]


def main():
    ms = sorted(p.split("metrics_")[1][:7] for p in glob.glob(str(ROOT / "data/interim/metrics_20*.parquet")))
    ym = ms[-1]
    d = pd.read_parquet(ROOT / f"data/interim/metrics_{ym}.parquet")
    p = d[d["pay_public"] & ~d["project_site"].fillna(False) & d["est_annual"].notna()]
    edges, counts = histogram(p["est_annual"])
    cap_year = lookup(load_caps(), ym, "upper_cap") * 12
    big = p[p["subs"] >= 1000]
    out = {"base_month": ym, "edges": edges, "counts": counts, "n": int(len(p)), "median": int(round(p["est_annual"].median())),
           "p25": int(round(p["est_annual"].quantile(.25))), "p75": int(round(p["est_annual"].quantile(.75))), "cap_annual": int(cap_year),
           "cap_near_share": round(float(p["cap_flag"].mean()), 4), "big": {"n": int(len(big)), "cap_near_share": round(float(big["cap_flag"].mean()), 4) if len(big) else None},
           "note": "국민연금 기준소득월액 연환산 추정(가입자 10명 이상 사업장). 실제 연봉이 아니며 상한 때문에 오른쪽 끝이 잘려 있다."}
    write_json(ROOT / "site/data/dist.json", out)
    print("dist", out["n"], out["median"], out["cap_annual"], out["big"])


if __name__ == "__main__":
    main()
