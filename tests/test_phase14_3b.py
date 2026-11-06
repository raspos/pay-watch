"""PHASE 14.3 후속 수정 테스트: (1) 보류된 DART 공시 급여 원본값의 공개 JSON 제거 (2) Release 업로드 전 예방 통제(publish_release)."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import make_test_bundle  # noqa: E402
import publish_release as pr  # noqa: E402

SITE = ROOT / "site"
CORP = SITE / "data/corp"
needs_site = pytest.mark.skipif(not CORP.exists(), reason="공개 데이터 없음(CI)")


def corp_records():
    out = {}
    for p in CORP.glob("*.json"):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


@needs_site
def test_held_dart_pay_values_are_removed_from_public_corp_json_but_firms_stay_searchable():
    recs = corp_records()
    held = {c: r for c, r in recs.items() if r.get("dart") and r["dart"].get("level") != "ok"}
    assert len(held) >= 300                                                                    # 보류 기업이 실제로 존재(검사가 공회전하지 않음)
    for c, r in held.items():
        d = r["dart"]
        assert d["avg"] is None and d["total"] is None and "consistency" not in d, c           # 급여 원본값·정합성 수치 제거
        assert d["level"] and d.get("pos") is None                                             # 상태(level)만 남고 비교집단 위치도 없음
    ok = [r["dart"] for r in recs.values() if r.get("dart") and r["dart"].get("level") == "ok"]
    assert ok and all(d["avg"] and d["total"] for d in ok)                                     # 유효한 값은 그대로
    rows = {r[0]: r for r in json.loads((SITE / "data/finder/entities.json").read_text(encoding="utf-8"))}
    assert all(c in rows for c in held)                                                        # 기업 자체는 검색 색인에 남아 있다


@needs_site
def test_saramin_fallback_value_stays_for_held_firms_and_is_marked_as_saramin():
    pay = {}
    for p in (SITE / "data/pay/s").glob("*.json"):
        pay.update(json.loads(p.read_text(encoding="utf-8")))
    recs = corp_records()
    both = [c for c, r in recs.items() if r.get("dart") and r["dart"].get("level") != "ok" and c in pay]
    assert both                                                                                # 보류 + 사람인 값 보유 기업이 있다
    assert all(pay[c]["v"] > 0 and pay[c]["y"] == 2025 for c in both)                          # 사람인 값은 유지(표시연도 포함)
    src = (ROOT / "web/js/corp.js").read_text(encoding="utf-8")
    assert "사람인 추정 · 표시연도" in src                                                      # 화면은 출처를 '사람인 추정'으로 구분


@needs_site
def test_public_check_rejects_held_pay_values_structurally(tmp_path):
    import check_public
    src = check_public.__file__
    text = Path(src).read_text(encoding="utf-8")
    assert "공시 급여 원본값(avg·total·consistency)이 공개 JSON 에 있음" in text              # 원자료 없이도(CI) 구조로 검사


@pytest.mark.skipif(not (ROOT / "data/raw/dart/cache").exists(), reason="원자료 캐시 없음(CI)")
def test_held_values_do_not_appear_in_own_public_records():
    import audit_held_exposure as a
    held = a.held_values()
    sd = SITE / "data"
    assert len(held) > 500
    assert a.structural_corp_check(sd) == [] and a.own_record_leaks(sd, held) == []            # 자기 법인·사람인 값 레코드에 보류값 없음


def fake_bundle(tmp, with_saramin, test=False, checks=("check_public", "check_links"), lie=False, tamper=False):
    b = tmp / "bundle"
    b.mkdir(parents=True, exist_ok=True)
    z = b / "pay-watch-site-v1.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("index.html", "x")
        zf.writestr("version.txt", "v1\n")
        if with_saramin:
            zf.writestr("data/pay/s/1.json", "{}")
    m = {"version": "v1", "zip": z.name, "zip_sha256": hashlib.sha256(z.read_bytes()).hexdigest(), "files": 3, "saramin_included": (with_saramin and not lie) or (lie and not with_saramin), "test_bundle": test, "checks": list(checks)}
    (b / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    if tamper:
        z.write_bytes(b"tampered")
    return b


def test_upload_gate_blocks_saramin_bundle_for_public_or_unknown_repo_without_permission(tmp_path):
    b = fake_bundle(tmp_path, True)
    ok, code, why, info = pr.evaluate(b, False, False)
    assert not ok and code == 2 and "공개" in why[0]                                           # 공개 저장소
    ok, code, why, _ = pr.evaluate(b, None, False)
    assert not ok and code == 2 and "fail-closed" in why[0]                                    # 공개 여부 확인 불가는 공개로 간주(fail-closed)
    ok, code, _, info = pr.evaluate(b, True, False)
    assert ok and info["gate"] == "private_storage"                                           # 비공개 저장소 보관만 허용
    ok, _, _, info = pr.evaluate(b, False, True)
    assert ok and info["gate"] == "permitted"                                                 # 권한 확인됨


def test_upload_gate_trusts_zip_contents_not_the_manifest_and_detects_tampering(tmp_path):
    ok, code, why, _ = pr.evaluate(fake_bundle(tmp_path / "a", True, lie=True), True, True)
    assert not ok and "zip 내용" in why[0]                                                     # manifest 가 거짓이면 권한이 있어도 차단
    ok, code, why, _ = pr.evaluate(fake_bundle(tmp_path / "b", False, lie=True), False, False)
    assert not ok and code == 1                                                               # 반대 방향의 불일치도 차단
    ok, code, why, _ = pr.evaluate(fake_bundle(tmp_path / "c", False, tamper=True), False, False)
    assert not ok and "sha256" in why[0]
    ok, code, why, _ = pr.evaluate(fake_bundle(tmp_path / "d", False, checks=()), False, False)
    assert not ok and "검사 기록" in why[0]                                                   # package_site 검사 없이 만든 실제 번들은 거부
    ok, _, _, info = pr.evaluate(fake_bundle(tmp_path / "e", False), False, False)
    assert ok and info["gate"] == "clean"                                                     # 사람인 없는 실제 번들은 공개 저장소에도 가능


def test_synthetic_test_bundle_is_always_allowed_even_when_repo_is_public_and_permission_unconfirmed(tmp_path):
    make_test_bundle.make(tmp_path / "t")
    ok, code, why, info = pr.evaluate(tmp_path / "t", False, False)
    assert ok and code == 0 and info["gate"] == "test"                                        # CI 검증용 소형 테스트 번들은 권한 미확인에서도 가능
    assert (json.loads((tmp_path / "t/manifest.json").read_text(encoding="utf-8")))["test_bundle"] is True


def test_main_is_dry_run_by_default_and_only_uploads_after_stamping(tmp_path):
    b = fake_bundle(tmp_path, False)
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = "false"
        return R()
    assert pr.main([str(b), "--repo", "o/r", "--tag", "t1", "--repo-private", "false"], runner=runner) == 0
    assert calls == [] and "preupload" not in json.loads((b / "manifest.json").read_text(encoding="utf-8"))   # dry-run: 업로드도 표시도 없음
    assert pr.main([str(b), "--repo", "o/r", "--tag", "t1", "--repo-private", "false", "--execute"], runner=runner) == 0
    m = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    assert m["preupload"]["checked"] is True and m["preupload"]["gate"] == "clean"            # 검증 표시 기록
    assert calls[-1][:4] == ["gh", "release", "create", "t1"] and "--repo" in calls[-1]
    blocked = fake_bundle(tmp_path / "s", True)
    calls.clear()
    assert pr.main([str(blocked), "--repo", "o/r", "--tag", "t2", "--repo-private", "false", "--execute"], runner=runner) == 2
    assert calls == [] and "preupload" not in json.loads((blocked / "manifest.json").read_text(encoding="utf-8"))   # 차단되면 어떤 업로드 명령도 실행되지 않는다


def test_visibility_unknown_is_treated_as_unknown(tmp_path):
    class R:
        returncode = 1
        stdout = ""
    assert pr.repo_visibility("o/r", runner=lambda *a, **k: R()) is None
    class T:
        returncode = 0
        stdout = "true\n"
    assert pr.repo_visibility("o/r", runner=lambda *a, **k: T()) is True


def test_pages_workflow_requires_the_preupload_stamp_for_real_bundles_only():
    w = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8"))
    steps = w["jobs"]["bundle"]["steps"]
    st = next(s for s in steps if "업로드 전 검증 표시" in s.get("name", ""))
    assert st["if"] == "steps.kind.outputs.test_bundle != 'true'" and "preupload" in st["run"] and "private_storage" in st["run"]
    names = [s.get("name", "") for s in steps]
    assert names.index(st["name"]) > next(i for i, n in enumerate(names) if "종류" in n)        # 번들 종류 판별 뒤
    g = (ROOT / ".github/workflows/release-guard.yml").read_text(encoding="utf-8")
    assert "보조" in g.split("name: release-guard")[0] and "publish_release.py" in g.split("name: release-guard")[0]   # 사후 삭제는 보조 장치임을 명시
    d = (ROOT / "docs/DEPLOY.md").read_text(encoding="utf-8")
    assert "publish_release.py" in d and "수동 업로드는 지원하지 않음" in d
