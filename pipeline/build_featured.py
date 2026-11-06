"""config/featured.yaml → site/data/featured.json. 이름이 정확히 일치하는 사업장만 연결하고, 못 찾으면 건너뛴다(깨진 링크 금지)."""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.export_public import search_key  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def resolve(items: list[dict], top_rows: list[list]) -> tuple[list[dict], list[str]]:
    """top_rows: [id, name, industry, loc, subs, pay, indiv]. match 키가 같은 사업장 중 가입자 최대 1곳."""
    by_key: dict[str, list] = {}
    for r in top_rows:
        by_key.setdefault(search_key(r[1]), []).append(r)
    out, missing = [], []
    for it in items:
        cands = by_key.get(search_key(it["match"]), [])
        if not cands:
            missing.append(it["label"])
            continue
        best = max(cands, key=lambda r: r[4])
        out.append({"label": it["label"], "id": best[0], "name": best[1]})
    return out, missing


def main():
    cfg = yaml.safe_load(open(ROOT / "config/featured.yaml", encoding="utf-8"))
    top = json.loads((ROOT / "site/data/index/top.json").read_text(encoding="utf-8"))
    items, missing = resolve(cfg["items"], top)
    import glob

    import pandas as pd
    ms = sorted(q.split("metrics_")[1][:7] for q in glob.glob(str(ROOT / "data/interim/metrics_20*.parquet")))
    if ms:
        m = pd.read_parquet(ROOT / f"data/interim/metrics_{ms[-1]}.parquet", columns=["est_annual", "cap_flag", "pay_public"])
        for it in items:
            r = m.loc[it["id"]] if it["id"] in m.index else None
            it["est"] = int(round(r["est_annual"])) if r is not None and r["pay_public"] and pd.notna(r["est_annual"]) else None
            it["cap"] = bool(r["cap_flag"]) if r is not None else None
    out = ROOT / "site/data/featured.json"
    out.write_text(json.dumps({"heading": cfg["heading"], "items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("featured", len(items), "missing", missing)


if __name__ == "__main__":
    main()
