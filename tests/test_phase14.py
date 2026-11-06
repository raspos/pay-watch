"""PHASE 14: 공개 데이터 정책(공시 값 의심 6곳 숨김)·대표 평균연봉 집계·통합 검색 색인·공개/연구용 분리를 데이터로 검증한다."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
need = [SITE / "data/finder/entities.json", ROOT / "reports/wage_model/phase12_firm_grades.csv"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in need), reason="공개 데이터 미생성")
needs_cache = pytest.mark.skipif(not (ROOT / "data/raw/dart/cache").exists(), reason="DART 원자료 캐시 없음(CI)")


def corp_records():
    out = {}
    for p in (SITE / "data/corp").glob("*.json"):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


@needs_cache
def test_doubt_firms_follow_raw_data_consistency_not_model_quality():
    """PHASE 14.1: 공시 값 의심 6곳 중 급여 원자료 정합성(≤5%)이 확인된 5곳은 공시 평균급여를 복원, 정합성이 깨진 1곳만 숨긴다. 평균근속 이상값은 숨긴다."""
    import apply_public_policy as pol
    emp = pol.emp_table(); recs = corp_records(); doubt = pol.doubt_codes()
    assert len(doubt) == 6
    shown = [c for c in doubt if recs[c]["dart"]]; hidden = [c for c in doubt if not recs[c]["dart"]]
    assert len(shown) == 5 and len(hidden) == 1 and all(pol.consistent(emp[c]) for c in shown) and not pol.consistent(emp[hidden[0]])
    assert all(recs[c].get("hold") == 1 for c in hidden) and not any(r.get("hold") for c, r in recs.items() if c not in hidden)
    assert all((r["dart"] or {}).get("tenure") is None or r["dart"]["tenure"] <= 45 for r in recs.values())


@needs_cache
def test_every_cached_firm_has_exactly_one_final_display_state():
    import audit_dart_display as a
    d, s = a.audit()
    assert s["firms"] == 3912 and sum(s["states"].values()) == 3912 and "INCONSISTENT" not in s["states"]
    assert s["model_only_hidden"] == 0 and s["usable_dart"] == 2444 and s["shown_total"] == 2071
    assert s["states"] == {"shown_page": 2010, "shown_dart_only": 61, "held_consistency": 373, "no_dart": 1468}


def test_representative_pay_count_matches_finder_flags_and_excludes_nps_estimates():
    recs = corp_records()
    valid = {c for c, r in recs.items() if r.get("dart") and r["dart"].get("level") == "ok" and r["dart"].get("avg")}
    valid |= set(json.loads((SITE / "data/finder/dart_only.json").read_text(encoding="utf-8")))      # 상세 페이지가 없는 기업의 공시 기록
    rows = json.loads((SITE / "data/finder/entities.json").read_text(encoding="utf-8"))
    flagged = {r[0] for r in rows if r[4] & 2}
    assert flagged == valid and len(valid) == 2071
    assert all(not (r[4] & 2) for r in rows if r[0] in recs and recs[r[0]].get("hold"))


def test_finder_entities_are_unique_codes_with_alias_dictionary_only_for_verified_rows():
    rows = json.loads((SITE / "data/finder/entities.json").read_text(encoding="utf-8"))
    dart = [r for r in rows if re.fullmatch(r"\d{8}", r[0])]                                  # PHASE 14.2 이후: DART 3,912 + 사람인 전용 1,551(별도 id)
    assert len(rows) == 5463 and len({r[0] for r in rows}) == 5463 and len(dart) == 3912
    aliased = [r for r in dart if r[2]]
    assert len(aliased) == 39
    names = {r[0]: r[1] for r in rows}
    import csv
    for r in csv.DictReader(open(ROOT / "config/search_aliases.csv", encoding="utf-8-sig")):
        assert names[r["dart_code"]] == r["legal_name"]           # 법적 명칭 원본 보존, 식별자 불변


def test_public_site_has_no_internal_research_data_and_publish_settings_are_explicit():
    cfg = (ROOT / "config/publish.yaml").read_text(encoding="utf-8")
    assert re.search(r"^publish_estimates:\s*true", cfg, re.M) and re.search(r"^saramin_permission:\s*confirmed", cfg, re.M)     # 공개 결정은 명시적 설정(2026-11-07 소유자 결정)
    assert (ROOT / "config/saramin_permission_evidence.md").exists()
    for p in (SITE / "data").rglob("*.json"):
        t = p.read_text(encoding="utf-8")
        for bad in ("saramin.co.kr", "csn=", "match_evidence", "quality_status", "phase12", "형태실험"):
            assert bad not in t, (p, bad)                                                       # 사람인 원본 URL·내부 매칭/품질 필드·연구 산출물 이름 없음
    assert not (SITE / "data/exp").exists() and (SITE / "robots.txt").exists()
