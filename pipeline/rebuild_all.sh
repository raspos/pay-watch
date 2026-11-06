#!/bin/sh
# 정규화 규칙이 바뀌었을 때 Stage 1 → ID → 지표 → 공개 JSON → 사이트를 일관되게 다시 만든다.
cd "$(dirname "$0")/.." || exit 1
for f in data/raw/nps/nps_20*.csv; do
  echo "stage1 $f"; python -X utf8 pipeline/run_stage1.py "$f" || exit 1
done
python -X utf8 pipeline/build_ids.py || exit 1
python -X utf8 pipeline/calculate_metrics.py || exit 1
python -X utf8 pipeline/export_json.py || exit 1
python -X utf8 pipeline/build_corp.py || exit 1
python -X utf8 pipeline/build_dist.py || exit 1
python pipeline/build_site.py
python -X utf8 pipeline/build_featured.py
echo REBUILD_DONE
