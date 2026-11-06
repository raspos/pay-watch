"""근속 구간별 집단 평균급여 추정(공개용 최소 데이터) 내보내기. 저장된 연구 결과만 사용한다(새 계산·새 수집 없음; 원본은 pipeline/export_exp.py 의 build_records).
공개 대상: 범위를 표시해도 되는 기업(내부 기준 A·B, 2,138곳)만. 나머지 기업(범위 없음·자료 부족·값 의심)은 파일에 아예 없다 → 화면에서 해당 영역이 그려지지 않는다.
공개 필드(기업당): b=기본 시나리오 5구간 [하한,상한](만원), x=확대 시나리오 5구간(없으면 null), cau=1 이면 '가정에 따라 결과가 크게 달라질 수 있음' 주의 표시, w=주의 사유 코드(주의 표시 기업만).
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


def enabled() -> bool:
    cfg = Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml")).read_text(encoding="utf-8")
    return re.search(r"^publish_estimates:\s*true", cfg, re.M) is not None


def build() -> dict:
    if not enabled():
        shutil.rmtree(OUT, ignore_errors=True)
        return {"publish_estimates": False}
    import export_exp
    recs = export_exp.build_records()
    shards: dict[int, dict] = {i: {} for i in range(SHARDS)}
    n = cau = held = 0
    for r in recs:
        if r["g"] not in ("A", "B") or not r["b"]:
            continue
        rec = {"b": r["b"], "x": r["x"], "cau": 1 if r["g"] == "B" else 0}
        if r["g"] == "B" and r["w"]:
            rec["w"] = r["w"]
        shards[int(r["c"]) % SHARDS][r["c"]] = rec
        n += 1; cau += rec["cau"]; held += r["x"] is None
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "s").mkdir(parents=True)
    for i, s in shards.items():
        (OUT / "s" / f"{i}.json").write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return {"publish_estimates": True, "firms": n, "with_caution": cau, "no_expanded": held}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
