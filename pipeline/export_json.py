"""metrics + 13개월 패널 → site/data 공개 JSON (인덱스·샤드·랭킹·메타). 네트워크·DART 불필요."""
import glob
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.export_public import (N_SHARDS, build_detail, export_indexes, meta, rankings, shard_of, write_json)  # noqa: E402
from paywatch.metrics import load_panel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data/interim"
OUT = ROOT / "site/data"


def config_tables():
    from paywatch.tables import load_caps, load_rates
    r, c = load_rates(), load_caps()
    rates = [{"from": x.effective_from, "to": x.effective_to, "total": float(x.total_rate), "verified": bool(str(x.verified_at).strip() and str(x.verified_at) != "nan")}
             for x in r.itertuples()]
    caps = [{"from": x.effective_from, "to": x.effective_to, "upper": int(x.upper_cap)} for x in c.itertuples()]
    return rates, caps


def meta_only():
    import json
    ms = sorted(p.split("nps_")[1][:7] for p in glob.glob(str(INTERIM / "nps_20*.parquet")))
    old = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    write_json(OUT / "meta.json", meta(ms, old["counts"], *config_tables()))
    print("meta.json 갱신")


def index_only():
    import json
    ms = sorted(p.split("nps_")[1][:7] for p in glob.glob(str(INTERIM / "nps_20*.parquet")))
    d = pd.read_parquet(INTERIM / f"metrics_{ms[-1]}.parquet")
    d = d[d["search_visible"]].copy()
    shutil.rmtree(OUT / "index", ignore_errors=True)
    stats = export_indexes(d, OUT)
    old = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    old["counts"].update(stats)
    write_json(OUT / "meta.json", old)
    print("index 재생성", stats)


def main():
    if "--meta-only" in sys.argv:
        return meta_only()
    if "--index-only" in sys.argv:
        return index_only()
    ms = sorted(p.split("nps_")[1][:7] for p in glob.glob(str(INTERIM / "nps_20*.parquet")))
    t = ms[-1]
    d = pd.read_parquet(INTERIM / f"metrics_{t}.parquet")
    d = d[d["search_visible"]].copy()
    P = load_panel(INTERIM, ms)
    import numpy as np
    for k, v in P.items():
        P[k] = v.reindex(d.index)
    est_cols = P["est_m"].to_numpy(dtype=float)
    subs, acq, lost, cap = (P[k].to_numpy(dtype=float) for k in ("subs", "acq", "lost", "cap"))
    if OUT.exists():
        shutil.rmtree(OUT)
    shards = defaultdict(dict)
    idx = {int(i): n for n, i in enumerate(d.index)}
    for r in d.assign(_id=d.index).to_dict("records"):
        i = r["_id"]
        n = idx[int(i)]
        rows = {"subs": subs[n], "acq": acq[n], "lost": lost[n], "est": est_cols[n], "cap": cap[n]}
        shards[shard_of(i)][str(int(i))] = build_detail(r, rows, ms)
    for k, v in shards.items():
        write_json(OUT / f"d/{k}.json", v)
    stats = export_indexes(d, OUT)
    write_json(OUT / "rankings.json", rankings(d))
    ind = pd.read_csv(INTERIM / f"industry_stats_{t}.csv", encoding="utf-8-sig")
    write_json(OUT / "industries.json", {str(r["ind2"]).zfill(2): {"name": r["업종"], "n": int(r["사업장"]), "med": round(float(r["중앙값"])),
                                                                 "cap": round(float(r["상한접근"]), 4), "g12": None if pd.isna(r["성장중앙"]) else round(float(r["성장중앙"]), 4),
                                                                 "lc12": None if pd.isna(r["상실중앙"]) else round(float(r["상실중앙"]), 4)} for _, r in ind.iterrows()})
    write_json(OUT / "meta.json", meta(ms, {"workplaces": len(d), "pay_public": int(d["pay_public"].sum()), **stats, "shards": len(shards)}, *config_tables()))
    print("exported", len(d), stats, "shards", len(shards))


if __name__ == "__main__":
    main()
