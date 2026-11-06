"""PAY RANK 공개 데이터: site/data/rank/rank.json — 평균연봉을 가진 기업의 압축 표(친구들 랭킹·기업별·업종별 순위 계산용). 기존 공개 데이터에서 파생하며 새 수집·새 모형 없음.
대표값 규칙은 결과 화면(web/js/pay-source.js)과 같다: 유효한 DART 공시 평균급여(level=ok) → 없으면 사람인 추정 → 없으면 행 없음. 급여 정합성으로 보류된 공시 원본값은 쓰지 않는다.
행: [id, 이름, 평균연봉(원), 출처(0=DART 공시, 1=사람인 추정), 연도, 업종 번호(-1=분류 없음), 지주회사 표시(0/1)]. 연봉 내림차순.
업종: 검증된 분류(고용노동부 산업 중분류; DART 업종코드 변환 오류 0건을 PHASE 12 에서 전수 확인)가 있는 DART 기업만. 사람인 전용·분류 없는 기업은 업종 순위에서 제외하며 임의로 분류하지 않는다(-1).
지주회사 표시: 이름에 지주·홀딩스·Holdings 가 있거나 PHASE 12 가 매핑 위험(지주 이름)으로 분류한 기업 — 평균급여 비교가 어렵다는 표시일 뿐 순위에서 빼지 않는다.
출력에는 등급·상태·내부 사유가 없다. config/publish.yaml 의 saramin_in_site 가 true 가 아니면 사람인 행은 넣지 않는다.
실행: python -I -X utf8 pipeline/build_rank.py"""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SD = ROOT / "site/data"
HOLD = re.compile(r"지주|홀딩스|holdings?", re.I)
MARKS = re.compile(r"\(주\)|주식회사|㈜|\(유\)|유한회사")


def short(legal: str) -> str:
    return re.sub(r"\s+", " ", MARKS.sub("", legal)).strip() or legal


def saramin_enabled() -> bool:
    cfg = Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml")).read_text(encoding="utf-8")
    return re.search(r"^saramin_in_site:\s*true", cfg, re.M) is not None


def build() -> dict:
    ents = json.loads((SD / "finder/entities.json").read_text(encoding="utf-8"))          # [id, legal, display, aliases, flags, size]
    name = {r[0]: (r[2] or short(r[1]), r[1]) for r in ents}
    dart = {}
    for p in (SD / "corp").glob("*.json"):
        for code, r in json.loads(p.read_text(encoding="utf-8")).items():
            d = r.get("dart")
            if d and d.get("level") == "ok" and d.get("avg"):
                dart[code] = (int(d["avg"]), int(d.get("fy") or 2025))
    for code, v in json.loads((SD / "finder/dart_only.json").read_text(encoding="utf-8")).items():
        dart[code] = (int(v["avg"]), int(v.get("fy") or 2025))
    sm = {}
    if saramin_enabled() and (SD / "pay/s").exists():
        for p in (SD / "pay/s").glob("*.json"):
            for pid, v in json.loads(p.read_text(encoding="utf-8")).items():
                sm[pid] = (int(v["v"]), int(v["y"]))
    g = pd.read_csv(ROOT / "reports/wage_model/phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    ind_of = {r.corp_code: r.노동부산업 for r in g.itertuples() if isinstance(r.노동부산업, str)}
    risky = set(g[g.사유.fillna("").str.contains("MAPPING_RISK_NAME")].corp_code)
    inds = sorted(set(ind_of.values()))
    idx = {n: i for i, n in enumerate(inds)}
    rows = []
    for pid, (disp, legal) in name.items():
        if pid in dart:
            pay, yr = dart[pid]; src = 0
        elif pid in sm:
            pay, yr = sm[pid]; src = 1
        else:
            continue
        ind = idx.get(ind_of.get(pid), -1) if re.fullmatch(r"\d{8}", pid) else -1
        hold = 1 if (HOLD.search(legal) or HOLD.search(disp) or pid in risky) else 0
        rows.append([pid, disp, pay, src, yr, ind, hold])
    rows.sort(key=lambda r: (-r[2], r[0]))
    out = SD / "rank"
    out.mkdir(parents=True, exist_ok=True)
    data = {"v": 1, "inds": inds, "rows": rows}
    (out / "rank.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"firms": len(rows), "dart": sum(1 for r in rows if r[3] == 0), "saramin": sum(1 for r in rows if r[3] == 1), "industries": len(inds), "with_industry": sum(1 for r in rows if r[5] >= 0), "holding": sum(r[6] for r in rows)}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
