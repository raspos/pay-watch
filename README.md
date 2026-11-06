# 내 친구는 얼마벌까? (PAY워치)

서비스명: **내 친구는 얼마벌까?** / 데이터 브랜드: **PAY워치**. 저장소·폴더·내부 명칭은 PAY워치 그대로이며, 이용자에게 보이는 이름만 바뀌었다.

내 회사 연봉, 진짜 신의 직장일까 — 국민연금·DART 공공데이터 기반 데이터저널리즘 프로젝트.

현재 단계: **Stage 4 (프론트엔드) 완료, 사용자 승인 대기**. 승인 전에는 다음 단계로 진행하지 않는다.

## 만들기
```
pip install -r requirements.txt
python -m pytest -q tests
sh pipeline/rebuild_all.sh        # Stage1(13개월) → ID → 지표 → 공개 JSON → site/
python pipeline/build_site.py     # web/ 만 다시 복사
python -m http.server 8790 --directory site
```
- 원본 CSV: `data/raw/nps/`(Git 제외), 해시 기록 `data/raw/nps/raw_manifest.csv`.
- 보험료율·상한: `config/nps_rates.csv`, `config/nps_caps.csv` (코드에 하드코딩 없음).
- DART 키는 `.env`(`DART_API_KEY`). 수집은 `pipeline/fetch_dart.py`(1건/초 이하, 단일 실행, 서킷 브레이커). 분당 1,000건 초과 시 1시간 차단된다는 제보가 있어 속도를 낮게 고정.
- 공개 JSON은 허용 목록 방식(`pipeline/paywatch/export_public.py`)으로만 내보낸다.
- 모든 급여 화면: "국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다."
