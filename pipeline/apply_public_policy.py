"""공개 데이터 정책 적용(공개용 site/data 후처리, 멱등). 근거는 DART 직원현황 캐시의 원자료(pipeline/paywatch/corp_layer.load_emp_table)다.
원칙(PHASE 14.1): 근속별 추정모형·산업 매핑의 품질 경고는 **공시 급여 표시를 막지 않는다**. 공시 평균급여 자체의 신뢰성(행별 평균과 급여총액÷인원의 불일치 5% 초과)에 문제가 있을 때만 보류한다.
 1) 평균근속이 45년을 넘는 값은 공개 화면에서 숨긴다(자료 오류 의심; 급여가 정상이어도 근속만 숨김).
 2) PHASE 12 'D 공시 값 의심' 6곳: 급여 정합성이 확인되면(일관성 ≤5%) 공시 평균급여를 원자료로 복원하고, 아니면 dart=null·hold=1 로 숨긴다.
 3) 급여 정합성 문제로 보류된 기업(level != ok)의 dart.avg·total·consistency 는 공개 JSON 에서 제거한다(avg·total 은 null, consistency 는 필드 삭제; level·연도·출처 링크는 유지).
 4) 국민연금 매칭이 없어 법인 상세 페이지가 없는 기업 중 급여 정합성이 확인된 곳은 site/data/finder/dart_only.json 에 공시 기록만 담는다(결과 화면이 대표 평균연봉을 보여줄 수 있게).
build_corp.py 로 법인 샤드를 다시 만든 뒤에는 반드시 다시 실행한다(pipeline/build_public.py 가 순서를 보장). 실행: python -I -X utf8 pipeline/apply_public_policy.py"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
SITE_DATA = ROOT / "site/data"
CONSISTENCY_OK = 0.05
TENURE_MAX = 45.0
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="


def doubt_codes() -> set[str]:
    g = pd.read_csv(ROOT / "reports/wage_model/phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    return set(g[(g.등급 == "D") & g.등급사유.str.contains("의심", na=False)].corp_code)


suppressed_codes = doubt_codes        # 이전 이름(호환)


def cache_codes() -> list[str]:
    g = pd.read_csv(ROOT / "reports/wage_model/phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    return list(g.corp_code)


def emp_table() -> dict:
    from paywatch.corp_layer import load_emp_table
    t = load_emp_table("2025")
    return {r["corp_code"]: r for r in t.to_dict("records")}


def consistent(e) -> bool:
    c = e.get("consistency")
    return bool(e.get("usable")) and c is not None and c == c and c <= CONSISTENCY_OK


def dart_record(e) -> dict:
    """corp_layer 의 공시 기록과 같은 형식(비교집단 위치 pos 는 만들지 않는다)."""
    ten = e.get("avg_tenure_weighted"); ten = None if ten is None or ten != ten or ten > TENURE_MAX else round(float(ten), 1)
    return {"fy": 2025, "employees": int(round(e["employees"])), "avg": int(round(e["avg_salary_derived"])), "total": int(round(e["salary_total"])), "tenure": ten,
            "consistency": round(float(e["consistency"]), 4), "level": "ok", "basis": e["basis"], "stlm": e["stlm_dt"], "src": DART_URL + str(e["rcept_no"]), "kind": "derived", "pos": None}


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, d) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def apply() -> dict:
    emp = emp_table(); doubt = doubt_codes(); restored = held = tenure_hidden = stripped = 0; in_shard: set[str] = set()
    for p in sorted((SITE_DATA / "corp").glob("*.json")):
        sh = _read(p); changed = False
        for code, r in sh.items():
            in_shard.add(code)
            d = r.get("dart")
            if code in doubt:
                e = emp.get(code)
                if e is not None and consistent(e):
                    r["dart"] = dart_record(e); r.pop("hold", None); restored += 1
                else:
                    r["dart"] = None; r["hold"] = 1; held += 1
                changed = True
            elif d and d.get("tenure") is not None and d["tenure"] > TENURE_MAX:
                d["tenure"] = None; tenure_hidden += 1; changed = True
            d = r.get("dart")
            if d and d.get("level") != "ok":                              # 급여 정합성 문제로 보류된 기업: 공시 급여 원본값(평균·총액)과 정합성 수치를 공개 JSON 에서 제거(내부 원자료·감사 기록에는 보존)
                if d.get("avg") is not None or d.get("total") is not None or "consistency" in d:
                    d["avg"] = None; d["total"] = None; d.pop("consistency", None); stripped += 1; changed = True
        if changed:
            _write(p, sh)
    only = {}
    for code in cache_codes():
        e = emp.get(code)
        if code not in in_shard and e is not None and consistent(e):
            r = dart_record(e); only[code] = {k: r[k] for k in ("fy", "employees", "avg", "tenure", "level", "stlm", "src")}
    (SITE_DATA / "finder").mkdir(parents=True, exist_ok=True)
    _write(SITE_DATA / "finder/dart_only.json", only)
    held_codes = sorted(c for c in doubt if not (emp.get(c) is not None and consistent(emp[c])))
    (ROOT / "config/public_policy_manifest.json").write_text(json.dumps({"tenure_max": TENURE_MAX, "doubt": sorted(doubt), "held": held_codes, "restored": sorted(set(doubt) - set(held_codes)), "dart_only": len(only)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"doubt_listed": len(doubt), "restored": restored, "held": held, "tenure_hidden": tenure_hidden, "held_pay_stripped": stripped, "dart_only_pages": len(only)}


if __name__ == "__main__":
    print(apply())
