"""통합 기업 찾기 색인(공개용): site/data/finder/entities.json. 이름·식별자·'자료 유무' 표시만 담는다(추정치·등급·상태 코드 없음).
- 대상: DART 캐시 3,912곳(reports/wage_model/phase12_firm_grades.csv 의 corp_code·기업명; 새 수집 없음).
- 별칭: config/search_aliases.csv(확인된 항목만). 모든 행의 dart_code 가 색인에 있고 legal_name 이 DART 기업명과 정확히 같아야 한다(아니면 빌드 실패).
- 행: [dart_code, legal_name, display_name, aliases(;구분), flags, size]
  flags 비트: 1=회사 상세 페이지 있음(site/data/corp), 2=대표 평균연봉(유효한 DART 공시 평균급여, 상세의 dart.level=ok) 있음, 4=국민연금 정보 있음(상세의 nps)
  플래그 8=사람인 평균연봉 있음(공개 설정으로 포함된 경우), 16=사람인에만 있는 기업(id 는 'S'+16진수 10자리, DART 코드 아님)
  size: 직원수(공시) 또는 국민연금 가입자 수 — 동순위 정렬용
실행: python -I -X utf8 pipeline/build_finder.py"""
import csv
import glob
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/finder"


def load_entities() -> dict:
    g = pd.read_csv(ROOT / "reports/wage_model/phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    assert g.corp_code.str.fullmatch(r"\d{8}").all() and not g.corp_code.duplicated().any(), "코드 형식·중복"
    ent = {r.corp_code: {"legal": r.기업명.strip(), "flags": 0, "size": 0} for r in g.itertuples()}
    for p in glob.glob(str(ROOT / "site/data/corp/*.json")):
        for code, v in json.load(open(p, encoding="utf-8")).items():
            if code not in ent:
                continue
            d = v.get("dart") or {}; n = v.get("nps") or {}
            ent[code]["flags"] = 1 | (2 if d.get("avg") and d.get("level") == "ok" else 0) | (4 if n else 0)
            ent[code]["size"] = int(d.get("employees") or n.get("subs") or 0)
    only = ROOT / "site/data/finder/dart_only.json"                      # 상세 페이지가 없지만 공시 평균급여가 확인된 기업(apply_public_policy.py)
    if only.exists():
        for code, v in json.loads(only.read_text(encoding="utf-8")).items():
            if code in ent:
                ent[code]["flags"] |= 2; ent[code]["size"] = int(v.get("employees") or 0)
    # 사람인(PHASE 14.2): 설정으로 포함된 경우에만 파일이 있다. DART 법인에 연결된 사람인 값이 있으면 SM(8) 비트, 사람인 전용 기업은 별도 행으로 합친다.
    sm_dir = ROOT / "site/data/pay/s"
    if sm_dir.exists():
        for p in sm_dir.glob("*.json"):
            for pid in json.loads(p.read_text(encoding="utf-8")):
                if pid in ent:
                    ent[pid]["flags"] |= 8
    return ent


def load_aliases(ent: dict) -> dict:
    out = {}
    with open(ROOT / "config/search_aliases.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            c = r["dart_code"].strip()
            assert re.fullmatch(r"\d{8}", c), f"별칭 사전 코드 형식: {c}"
            assert c in ent, f"별칭 사전의 코드가 DART 캐시 색인에 없음: {c}"
            assert ent[c]["legal"] == r["legal_name"].strip(), f"법적 명칭 불일치({c}): 사전 {r['legal_name']} / DART {ent[c]['legal']}"
            assert c not in out, f"별칭 사전 코드 중복: {c}"
            out[c] = (r["display_name"].strip(), [a.strip() for a in r["aliases"].split(";") if a.strip()])
    return out


def build() -> dict:
    ent = load_entities(); al = load_aliases(ent)
    rows = []
    for c, e in sorted(ent.items()):
        disp, aliases = al.get(c, (None, []))
        rows.append([c, e["legal"], disp or "", ";".join(aliases), e["flags"], e["size"]])
    smf = OUT / "sm_entities.json"                                                   # 사람인 전용 기업(DART 코드 없음): 사람인 csn 해시 id 행
    if smf.exists():
        sm_rows = json.loads(smf.read_text(encoding="utf-8"))
        assert all(re.fullmatch(r"S[0-9a-f]{10}", r[0]) and len(r) == 6 for r in sm_rows) and not {r[0] for r in sm_rows} & {r[0] for r in rows}, "사람인 전용 행 형식·중복"
        rows += sm_rows
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "entities.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"entities": len(rows), "aliased": len(al), "with_page": sum(1 for r in rows if r[4] & 1), "disclosed_pay": sum(1 for r in rows if r[4] & 2), "nps": sum(1 for r in rows if r[4] & 4), "saramin_value": sum(1 for r in rows if r[4] & 8), "saramin_only": sum(1 for r in rows if r[4] & 16)}


if __name__ == "__main__":
    print(build())
