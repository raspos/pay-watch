"""PHASE 14.1: DART 공시 평균급여 표시 누락 감사. 캐시 3,912곳이 **정확히 하나의 최종 표시 상태**에 속하는지 원자료(직원현황 캐시)와 공개 데이터(site/data)로 확인한다.
상태: shown_page(법인 상세 + 대표 평균연봉) / shown_dart_only(상세 없음, 공시 기록으로 표시) / held_consistency(원자료 급여 정합성 5% 초과 → 보류) / no_dart(직원현황 없음·급여 계산 불가).
'모형 품질만 문제인 기업'(근속 추정 경고·산업 매핑 의심으로 공시값까지 숨겨진 곳)은 최종 상태에서 0이어야 한다.
결과: reports/phase14_1_display_states.csv, 집계 JSON 출력. 실행: python -I -X utf8 pipeline/audit_dart_display.py"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import apply_public_policy as pol  # noqa: E402


def audit() -> tuple[pd.DataFrame, dict]:
    g = pd.read_csv(ROOT / "reports/wage_model/phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    emp = pol.emp_table(); recs = {}
    for p in (ROOT / "site/data/corp").glob("*.json"):
        recs.update(json.loads(p.read_text(encoding="utf-8")))
    only = json.loads((ROOT / "site/data/finder/dart_only.json").read_text(encoding="utf-8"))
    rows = []
    for r in g.itertuples():
        c = r.corp_code; e = emp.get(c); usable = bool(e is not None and e.get("usable")); cons_ok = bool(e is not None and pol.consistent(e))
        page = recs.get(c); shown_page = bool(page and page.get("dart") and page["dart"].get("level") == "ok" and page["dart"].get("avg"))
        shown_only = c in only
        if shown_page and not shown_only: state = "shown_page"
        elif shown_only and page is None: state = "shown_dart_only"
        elif usable and not cons_ok and not shown_page and not shown_only: state = "held_consistency"
        elif not usable and not shown_page and not shown_only: state = "no_dart"
        else: state = "INCONSISTENT"
        model_only_hidden = usable and cons_ok and not (shown_page or shown_only)
        rows.append({"corp_code": c, "name": r.기업명, "state": state, "usable": usable, "consistency_ok": cons_ok, "has_page": page is not None, "grade": r.등급, "model_only_hidden": model_only_hidden})
    d = pd.DataFrame(rows)
    summary = {"firms": len(d), "states": d.state.value_counts().to_dict(), "usable_dart": int(d.usable.sum()), "model_only_hidden": int(d.model_only_hidden.sum()),
               "shown_total": int(d.state.isin(["shown_page", "shown_dart_only"]).sum())}
    return d, summary


if __name__ == "__main__":
    d, s = audit()
    d.drop(columns=["model_only_hidden"]).to_csv(ROOT / "reports/phase14_1_display_states.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(s, ensure_ascii=False))
    assert "INCONSISTENT" not in s["states"] and sum(s["states"].values()) == s["firms"] and s["model_only_hidden"] == 0
