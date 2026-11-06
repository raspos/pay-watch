"""'우리 회사보다 잘 주는 곳' 데이터: 비교집단별 상위 목록(국민연금 추정, 상한 비접근만)을 64개 샤드로 내보내고,
사업장 상세(peer.gid)에 집단 번호를 붙인다. export_json.py 다음, build_corp.py 이전에 실행한다. 네트워크 호출 없음."""
import glob
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.export_public import write_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site/data"
PEER_SHARDS = 64


def main():
    ym = sorted(p.split("metrics_")[1][:7] for p in glob.glob(str(ROOT / "data/interim/metrics_20*.parquet")))[-1]
    groups = json.loads((ROOT / f"data/interim/peer_groups_{ym}.json").read_text(encoding="utf-8"))["groups"]
    out = SITE / "peers/n"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    shards = {}
    for gid, g in groups.items():
        shards.setdefault(int(gid) % PEER_SHARDS, {})[gid] = g
    for k, v in shards.items():
        write_json(out / f"{k}.json", v)

    d = pd.read_parquet(ROOT / f"data/interim/metrics_{ym}.parquet", columns=["peer_gid"])
    m = d["peer_gid"].dropna().astype(int)
    bysh = {}
    for wp, gid in m.items():
        bysh.setdefault(int(wp) % 1024, {})[str(int(wp))] = int(gid)
    patched = 0
    for sh, items in bysh.items():
        p = SITE / f"d/{sh}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for wid, gid in items.items():
            if wid in data and data[wid].get("peer"):
                data[wid]["peer"]["gid"] = gid
                patched += 1
        write_json(p, data)
    meta = json.loads((SITE / "meta.json").read_text(encoding="utf-8"))
    meta["counts"]["peer_groups"] = len(groups)
    write_json(SITE / "meta.json", meta)
    print("peer groups", len(groups), "shards", len(shards), "workplaces with gid", patched)


if __name__ == "__main__":
    main()
