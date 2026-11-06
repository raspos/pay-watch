"""PHASE 14.2 사람인 통합: 대표값 선택·식별자·오매칭 방지·공개 최소 필드·권한 게이트·분리를 산출물로 검증한다(관련 테스트만; 전체 실행은 단계 종료 시 한 번)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SRC = ROOT.parent / "saramin-experiment" / "data"
need = [SITE / "data/pay/s/0.json", SITE / "data/finder/sm_entities.json", ROOT / "reports/phase14_2_rep_selection.csv"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in need), reason="사람인 통합 산출물 없음")
PY = [sys.executable, "-I", "-X", "utf8"]


def shard_values():
    out = {}
    for p in (SITE / "data/pay/s").glob("*.json"):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


def test_identifiers_unique_and_no_invented_dart_codes():
    rows = json.loads((SITE / "data/finder/entities.json").read_text(encoding="utf-8"))
    ids = [r[0] for r in rows]
    assert len(ids) == len(set(ids)) == 5463
    dart = [i for i in ids if re.fullmatch(r"\d{8}", i)]
    sm = [i for i in ids if not re.fullmatch(r"\d{8}", i)]
    assert len(dart) == 3912 and len(sm) == 1551 and all(re.fullmatch(r"S[0-9a-f]{10}", i) for i in sm)          # 사람인 전용 기업에 임의의 DART 코드를 만들지 않는다
    flags = {r[0]: r[4] for r in rows}
    assert all(flags[i] & 16 and flags[i] & 8 and not flags[i] & 1 for i in sm)                                    # 사람인 전용: 법인 상세·DART 값 없음
    assert not any(flags[i] & 16 for i in dart)


def test_representative_selection_follows_priority_and_records_reason():
    rep = pd.read_csv(ROOT / "reports/phase14_2_rep_selection.csv", dtype=str, keep_default_na=False)
    assert len(rep) == 5463 and rep.id.is_unique
    d = rep[rep.rep_source == "dart"]
    assert len(d) == 2071 and (d.reason == "dart_valid").all() and d.dart_state.isin(["shown_page", "shown_dart_only"]).all()
    s = rep[(rep.rep_source == "saramin") & (rep.kind == "dart")]
    assert s.dart_state.isin(["no_dart", "held_consistency"]).all()                                                 # 유효한 DART 가 있으면 사람인으로 대체하지 않는다
    assert set(s.reason) <= {"dart_missing", "dart_held_quality"} and (s.saramin_won != "").all()
    none = rep[rep.rep_source == "none"]
    assert (none.saramin_won == "").all() and (none.dart_won == "").all()                                           # 자료가 없으면 값 없음
    assert (rep.rep_source != "none").sum() == len(d) + len(s) + (rep.kind == "saramin_only").sum() == 4000
    cj = rep[rep.id == "00148540"].iloc[0]
    assert cj.rep_source == "dart" and cj.reason == "dart_valid"                                                    # 이례적 공시값(CJ)도 사람인으로 자동 대체하지 않는다


def test_public_values_are_minimal_and_match_saramin_raw_source():
    vals = shard_values()
    assert len(vals) == 2326 and all(set(v) == {"v", "y"} and v["y"] == 2025 and isinstance(v["v"], int) and v["v"] > 0 for v in vals.values())
    if (SRC / "saramin_all_enterprises.csv").exists():
        raw = pd.read_csv(SRC / "saramin_all_enterprises.csv", encoding="utf-8-sig", dtype=str)
        by_total = set(raw.average_salary.astype(float).astype(int))
        assert all(v["v"] in by_total for v in vals.values())                                                       # 사람인 원본값 그대로(변환·덮어쓰기 없음)
    text = "".join(p.read_text(encoding="utf-8") for p in (SITE / "data/pay/s").glob("*.json")) + (SITE / "data/finder/sm_entities.json").read_text(encoding="utf-8")
    for bad in ("saramin.co.kr", "csn=", "SARAMIN_", "match_evidence", "quality_status", "NORMALIZED_NAME", "AFFILIATE"):
        assert bad not in text


def test_match_audit_blocks_affiliate_and_name_collisions():
    a = pd.read_csv(ROOT / "reports/phase14_2_match_audit.csv", dtype=str, keep_default_na=False)
    linked = a[a.dart != ""]
    assert set(linked[linked.decision == "accept"].evidence) <= {"OFFICIAL_ALIAS_MATCH", "NORMALIZED_NAME_EXACT_1TO1"}   # 이름 기반 매칭은 근거를 구분해 기록, 계열사 휴리스틱은 DART 법인에 연결하지 않는다
    aff = a[a.evidence.str.startswith("AFFILIATE_HEURISTIC")]
    assert len(aff) > 0 and (aff.dart == "").all()                                                                  # 계열사는 모회사와 병합하지 않고 사람인 전용으로
    q = a[a.decision == "quarantine"]
    assert len(q) == 6 and set(q.reason.str.replace(r"=.*", "", regex=True)) <= {"name_collision_among_saramin", "name_collision_with_dart", "ratio_vs_dart"}
    accepted = set(shard_values())
    for _, r in q.iterrows():                                                                                       # 격리된 기업은 공개 값에 없다
        assert (r.dart or r.get("public_id", "")) not in accepted or not (r.dart or r.get("public_id", ""))


def run_check(cfg_text, tmp_path):
    cfg = tmp_path / "publish.yaml"
    cfg.write_text(cfg_text, encoding="utf-8")
    return subprocess.run(PY + [str(ROOT / "pipeline/check_public.py")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PAYWATCH_PUBLISH_CONFIG": str(cfg), "PAYWATCH_SKIP_RAW_CHECK": "1"})


def test_permission_gate_blocks_deploy_until_confirmed(tmp_path):
    base = "publish_experimental: false\nsaramin_in_site: true\ncontact: null\n"
    blocked = run_check(base + "saramin_permission: unconfirmed\n", tmp_path)
    assert blocked.returncode == 2 and "배포 차단" in blocked.stdout and "실패 0건" in blocked.stdout                   # 권한 미확인: 데이터 누출은 없지만 배포 차단
    assert run_check(base + "saramin_permission: confirmed\n", tmp_path).returncode == 0
    off = run_check("publish_experimental: false\nsaramin_in_site: false\nsaramin_permission: unconfirmed\ncontact: null\n", tmp_path)
    assert off.returncode == 1 and "saramin_in_site=false" in off.stdout                                           # 제외 설정인데 파일이 남아 있으면 실패
    assert run_check("publish_experimental: true\nsaramin_in_site: true\nsaramin_permission: confirmed\n", tmp_path).returncode == 1


def test_exporter_reads_the_exclusion_setting(tmp_path):
    cfg = tmp_path / "publish.yaml"
    cfg.write_text("saramin_in_site: false\n", encoding="utf-8")
    code = "import sys; sys.path.insert(0, 'pipeline'); import build_saramin as b; print(b.config()['saramin_in_site'])"
    r = subprocess.run(PY + ["-c", code], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PAYWATCH_PUBLISH_CONFIG": str(cfg), "PAYWATCH_SKIP_RAW_CHECK": "1"})
    assert r.stdout.strip() == "false"


def test_research_estimates_stay_separate_from_representative_pay():
    """근속별 추정(연구용 preview 전용)은 대표 평균연봉 선택 로직과 코드·데이터가 분리돼 있다."""
    src = (ROOT / "web/js/pay-source.js").read_text(encoding="utf-8")
    assert "exp-" not in src and "range" not in src
    for p in SITE.rglob("*.js"):
        assert "exp-section" not in p.read_text(encoding="utf-8", errors="ignore"), p
    assert not (SITE / "data/exp").exists()
