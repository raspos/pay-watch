"""PHASE 14.3 차이 목록(기존 산출물만 사용, 파이프라인 재실행 없음).
1) PHASE 14.1 의 DART 급여 보류 373곳 vs 사람인 통합 데이터의 DART 채택 집합 안에서 보류 상태인 371곳: 기업 ID 별 차이와 이유
2) 사람인 통합 5,468곳 vs PAY워치 통합 5,463곳: 기업 ID 별 차이와 이유
결과: reports/phase14_3_diff_lists.csv(+ 표준 출력 요약). 실행: python -I -X utf8 pipeline/diff_reports.py"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "saramin-experiment" / "data"


def build() -> tuple[pd.DataFrame, dict]:
    states = pd.read_csv(ROOT / "reports/phase14_1_display_states.csv", encoding="utf-8-sig", dtype={"corp_code": str}).set_index("corp_code")
    integ = pd.read_csv(SRC / "paywatch_integrated_final.csv", encoding="utf-8-sig", dtype=str)
    audit = pd.read_csv(ROOT / "reports/phase14_2_match_audit.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    rep = pd.read_csv(ROOT / "reports/phase14_2_rep_selection.csv", encoding="utf-8-sig", dtype=str, keep_default_na=False).set_index("id")
    rows = []
    # 1) 보류 373 vs 371
    held = set(states[states.state == "held_consistency"].index)
    their_dart = set(integ[integ.salary_source == "DART_DISCLOSURE"].dart_corp_code)
    by_code = integ.dropna(subset=["dart_corp_code"]).set_index("dart_corp_code")
    in_their = held & their_dart
    for c in sorted(held - their_dart):
        r = by_code.loc[c]
        why = {"NO_DATA": "사람인 통합 집계에서 DART 평균급여 자체가 누락(급여 정합성 5% 초과 기업이라 PAY워치는 보류)", "P12_INVALID_EXCLUDED": "PHASE 12 공시 값 의심 6곳 중 급여 원자료 정합성도 깨진 기업: 사람인 통합은 제외, PAY워치도 보류 유지"}.get(r.quality_status, r.quality_status)
        rows.append({"list": "dart_held_373_vs_371", "id": c, "name": r.display_name, "status": f"held_in_paywatch_not_in_saramin_dart({r.quality_status})", "reason": why})
    # 2) 5,468 vs 5,463
    ids_theirs = set(integ.company_id)
    mine = set(rep.index)
    def cid(i):
        return f"DART_{i}" if i.isdigit() else None
    mine_ids = {cid(i) or i for i in mine}
    q = audit[(audit.decision == "quarantine") & (audit.dart == "")]
    for r in q.itertuples():
        rows.append({"list": "entities_5468_vs_5463", "id": r.company_id, "name": r.name, "status": "excluded_from_paywatch_index", "reason": {"name_collision_among_saramin": "사람인 전용 기업끼리 정규화 이름이 같아 동일 기업 중복 노출을 막기 위해 함께 격리", "name_collision_with_dart": "DART 법인과 정규화 이름이 같아 별개 법인으로 확정할 수 없어 격리(자동 병합 금지)"}.get(r.reason, r.reason)})
    summary = {"held_paywatch": len(held), "held_inside_saramin_dart_set": len(in_their), "held_diff": len(held - their_dart),
               "saramin_rows": len(integ), "paywatch_entities": len(rep), "excluded_sm_only": len(q),
               "unaccounted_in_5468_vs_5463": len(integ) - len(rep) - len(q)}
    return pd.DataFrame(rows), summary


if __name__ == "__main__":
    df, s = build()
    df.to_csv(ROOT / "reports/phase14_3_diff_lists.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(s, ensure_ascii=False))
    print(df.groupby(["list", "reason"]).size().to_string())
