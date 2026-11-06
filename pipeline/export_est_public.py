"""근속 구간별 집단 평균급여 추정(공개용 최소 데이터) 내보내기. 저장된 연구 결과만 사용한다(새 계산·새 수집 없음; 원본은 pipeline/export_exp.py 의 build_records).
공개 대상: 범위를 표시해도 되는 기업(내부 기준 A·B, 2,138곳)만. 나머지 기업(범위 없음·자료 부족·값 의심)은 파일에 아예 없다 → 화면에서 해당 영역이 그려지지 않는다.
공개 필드(기업당): b=기본 시나리오 5구간 [하한,상한](만원), x=확대 시나리오 5구간(없으면 null), cau=1 이면 '가정에 따라 결과가 크게 달라질 수 있음' 주의 표시, w=주의 사유 코드(주의 표시 기업만), y=추정 기준연도, m=모형 버전. 결과 제공 가능 여부=레코드 존재(없으면 제공 안 함). 구간 순서는 meta.json 의 bins.
입력 점검: 추정은 DART 공시 평균급여를 입력으로 쓰므로, 급여 정합성 문제로 보류된 공시값(level != ok)에서 만들어진 추정은 공개하지 않는다(보류 기업 제외).
내부 품질 등급 글자·상태 코드·기업 공시 평균(a)·평균근속·직원 수·산업 정보는 공개 파일에 넣지 않는다(공시 평균은 결과 화면이 보여도 되는 값만 그래프에 넘긴다).
출력: site/data/est/s/<코드%64>.json. config/publish.yaml 의 publish_estimates 가 true 가 아니면 파일을 만들지 않고 기존 파일도 지운다.
실행: python -I -X utf8 pipeline/export_est_public.py"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
OUT = ROOT / "site/data/est"
SHARDS = 64
MODEL_VERSION = "phase10-d2-shape-v1"      # PHASE 10 형태 불확실성 모형(D-2 F1/F2 × m10 격자, 확대 시나리오 포함), 원자료 정밀도 재계산(PHASE 12)
REF_YEAR = 2025                            # 산업 임금곡선·DART 공시 기준연도
BIN_LABELS = ["1년 미만", "1~3년", "3~5년", "5~10년", "10년 이상"]


def enabled() -> bool:
    cfg = Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml")).read_text(encoding="utf-8")
    return re.search(r"^publish_estimates:\s*true", cfg, re.M) is not None


def build() -> dict:
    if not enabled():
        shutil.rmtree(OUT, ignore_errors=True)
        return {"publish_estimates": False}
    import export_exp
    sd = ROOT / "site/data"
    ok = set(json.loads((sd / "finder/dart_only.json").read_text(encoding="utf-8")))            # 상세 페이지 없이 공시 기록만 있는 기업(정합성 통과)
    for p in (sd / "corp").glob("*.json"):
        for code, r in json.loads(p.read_text(encoding="utf-8")).items():
            if r.get("dart") and r["dart"].get("level") == "ok" and r["dart"].get("avg"):
                ok.add(code)
    recs = export_exp.build_records()
    shards: dict[int, dict] = {i: {} for i in range(SHARDS)}
    n = cau = held = excluded_held = 0
    for r in recs:
        if r["g"] not in ("A", "B") or not r["b"]:
            continue
        if r["c"] not in ok:                                                                    # 입력인 공시 평균급여가 보류됐거나 확인되지 않은 기업은 제외
            excluded_held += 1
            continue
        rec = {"b": r["b"], "x": r["x"], "cau": 1 if r["g"] == "B" else 0, "y": REF_YEAR, "m": MODEL_VERSION}
        if r["g"] == "B" and r["w"]:
            rec["w"] = r["w"]
        shards[int(r["c"]) % SHARDS][r["c"]] = rec
        n += 1; cau += rec["cau"]; held += r["x"] is None
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "s").mkdir(parents=True)
    for i, s in shards.items():
        (OUT / "s" / f"{i}.json").write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    (OUT / "meta.json").write_text(json.dumps({"model_version": MODEL_VERSION, "ref_year": REF_YEAR, "bins": BIN_LABELS, "unit": "만원(연환산 집단 평균급여의 시나리오 범위)", "firms": n,
                                              "note": "개인 연봉이나 통계적 신뢰구간이 아닌 근속 구간 집단 평균급여의 시나리오 추정 범위. 정확도는 검증되지 않음."}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"publish_estimates": True, "firms": n, "with_caution": cau, "no_expanded": held, "excluded_dart_pay_held_or_unverified": excluded_held}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
