"""PHASE 14.3: GitHub Pages 배포 구조·저장소 보호·번들 검증·사람인 직접 검사를 점검한다(관련 테스트만; 실제 배포는 하지 않는다)."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import guard_repo  # noqa: E402
import package_site  # noqa: E402
import verify_bundle  # noqa: E402


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8"))


def steps_text(job):
    return "\n".join(f"{s.get('name', '')} {s.get('run', '')} {s.get('uses', '')}" for s in job["steps"])


def test_workflow_is_manual_only_and_deploys_only_real_bundles():
    w = workflow(); on = w.get("on", w.get(True))
    assert "push" not in on and "schedule" not in on and set(on) == {"pull_request", "workflow_dispatch"}      # 자동 배포 없음
    assert "release_tag" in on["workflow_dispatch"]["inputs"]
    b, d = w["jobs"]["bundle"], w["jobs"]["deploy"]
    assert b["needs"] == "verify-source" and "release_tag" in b["if"] and "workflow_dispatch" in b["if"]
    assert d["needs"] == "bundle" and d["if"] == "needs.bundle.outputs.test_bundle == 'false'"                 # 테스트 번들은 배포 job 에 올 수 없다
    assert d["permissions"] == {"pages": "write", "id-token": "write"}
    assert w["permissions"] == {"contents": "read"}                                                              # 기본 권한 최소
    assert "pages" not in w["jobs"]["verify-source"].get("permissions", {}) and "pages" not in b.get("permissions", {})


def test_workflow_runs_all_required_checks_and_never_pages_deploys_test_bundles():
    w = workflow(); v, bt = steps_text(w["jobs"]["verify-source"]), steps_text(w["jobs"]["bundle"])
    for needle in ("guard_repo.py", "node --test", "pytest"):
        assert needle in v
    for needle in ("verify_bundle.py", "check_public.py", "check_links.py", "saramin_permission", "site/data/pay", "sm_entities.json", "test_bundle", "upload-artifact", "upload-pages-artifact"):
        assert needle in bt                                                                                        # 사람인 직접 검사(파일 존재) + 종료 코드 검사 + 테스트 번들 분기
    steps = w["jobs"]["bundle"]["steps"]
    pages_up = next(s for s in steps if "upload-pages-artifact" in s.get("uses", ""))
    test_up = next(s for s in steps if "upload-artifact@" in s.get("uses", ""))
    assert pages_up["if"] == "steps.kind.outputs.test_bundle != 'true'" and pages_up["with"]["path"] == "site"    # 실제 번들만 Pages 아티팩트, 대상은 site/ 하나
    assert test_up["if"] == "steps.kind.outputs.test_bundle == 'true'" and test_up["with"]["retention-days"] == 1  # 테스트 번들은 점검용 아티팩트(1일)로만
    names = [s.get("name", "") for s in steps]
    kind = next(i for i, n in enumerate(names) if "종류" in n)
    for key in ("공개 빌드 검사", "링크·경로"):
        assert next(i for i, n in enumerate(names) if key in n) > kind                                            # 번들 종류 판별 뒤에 검사
    assert not any("deploy-pages" in s.get("uses", "") for s in steps)                                           # deploy-pages 는 deploy job 에만


def test_release_guard_workflow_unpublishes_and_deletes_assets_on_violation():
    g = yaml.safe_load((ROOT / ".github/workflows/release-guard.yml").read_text(encoding="utf-8"))
    on = g.get("on", g.get(True))
    assert on == {"release": {"types": ["published", "edited"]}} and g["permissions"] == {"contents": "write"}
    t = steps_text(g["jobs"]["guard"])
    assert "release_guard.py" in t and "--draft" in t and "delete-asset" in t and "github.event.repository.private" in t and "saramin_permission" in t


def test_repo_guard_passes_on_real_tree_and_gitignore_blocks_generated_outputs():
    assert guard_repo.check(ROOT) == []
    g = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for need in ("site/", "dist/", "data/", "preview/", "reports/phase14_2_*", ".env"):
        assert need in g


def make_tree(tmp, files, ignore=""):
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / ".gitignore").write_text(ignore, encoding="utf-8")
    for rel, size in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)
    return tmp


def test_repo_guard_blocks_site_saramin_data_internal_audit_raw_and_large_files(tmp_path):
    t = make_tree(tmp_path, {"site/data/pay/s/0.json": 5, "site/index.html": 5, "reports/phase14_2_match_audit.csv": 5, "data/raw/x.csv": 5, "saramin_all_enterprises.csv": 5,
                             "paywatch_integrated_final.json": 5, ".env": 5, "web/js/saramin.js": 5, "pipeline/build_saramin.py": 5, "docs/notes.md": 5, "big.bin": 26 * 1024 * 1024})
    bad = "\n".join(guard_repo.check(t))
    for flagged in ("site/data/pay/s/0.json", "site/index.html", "reports/phase14_2_match_audit.csv", "data/raw/x.csv", "saramin_all_enterprises.csv", "paywatch_integrated_final.json", ".env", "big.bin"):
        assert flagged in bad, flagged
    assert "web/js/saramin.js" not in bad and "pipeline/build_saramin.py" not in bad and "docs/notes.md" not in bad      # 사람인 관련 코드·문서는 허용
    ignoring = make_tree(tmp_path / "ok", {"site/data/pay/s/0.json": 5, "data/raw/x.csv": 5, "web/index.html": 5}, ignore="site/\ndata/\n")
    assert guard_repo.check(ignoring) == []                                                                         # .gitignore 가 걸러내면 통과


def test_package_gate_requires_confirmed_permission_and_evidence_file(tmp_path):
    site = tmp_path / "site"
    (site / "data/pay/s").mkdir(parents=True)
    assert package_site.saramin_present(site) and not package_site.saramin_present(tmp_path)
    ev = tmp_path / "evidence.md"
    assert not package_site.saramin_allowed("saramin_permission: confirmed\n", ev)                                   # 근거 파일 없음
    ev.write_text("짧은 메모", encoding="utf-8")
    assert not package_site.saramin_allowed("saramin_permission: confirmed\n", ev)                                   # 근거가 너무 짧음
    ev.write_text("허락 근거 " * 30, encoding="utf-8")
    assert package_site.saramin_allowed("saramin_permission: confirmed\n", ev)
    assert not package_site.saramin_allowed("saramin_permission: unconfirmed\n", ev)                                 # 근거 파일이 있어도 설정이 확인 상태가 아니면 차단
    assert not (ROOT / "config/saramin_permission_evidence.md").exists()                                              # 현재 권한 미확인: 근거 파일이 없다


def test_package_main_blocks_current_site_without_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYWATCH_SKIP_RAW_CHECK", "1")
    if not (ROOT / "site/data/pay").exists():
        pytest.skip("사람인 데이터가 포함된 site/ 없음")
    assert package_site.main(["--dry-run", "--out", str(tmp_path)]) == 2
    assert not list(tmp_path.glob("*.zip"))                                                                         # 차단되면 번들이 만들어지지 않는다


def make_bundle(tmp, files, files_count=None, version="v1"):
    b = tmp / "bundle"
    b.mkdir()
    z = b / f"pay-watch-site-{version}.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for n, c in files.items():
            zf.writestr(n, c)
    m = {"version": version, "zip": z.name, "zip_sha256": hashlib.sha256(z.read_bytes()).hexdigest(), "files": files_count or len(files)}
    (b / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return b


def test_bundle_verification_detects_tampering_and_mismatch(tmp_path):
    good = make_bundle(tmp_path / "a", {"index.html": "x", "version.txt": "v1\n"}) if (tmp_path / "a").mkdir() is None else None
    assert verify_bundle.verify(good, tmp_path / "a" / "out") == []
    (tmp_path / "b").mkdir()
    bad = make_bundle(tmp_path / "b", {"index.html": "x", "version.txt": "v1\n"})
    (bad / "pay-watch-site-v1.zip").write_bytes(b"tampered")
    assert "sha256" in verify_bundle.verify(bad, tmp_path / "b" / "out")[0]
    (tmp_path / "c").mkdir()
    cnt = make_bundle(tmp_path / "c", {"index.html": "x", "version.txt": "v1\n"}, files_count=5)
    assert any("파일 수" in e for e in verify_bundle.verify(cnt, tmp_path / "c" / "out"))
    (tmp_path / "d").mkdir()
    ver = make_bundle(tmp_path / "d", {"index.html": "x", "version.txt": "v2\n"}, version="v1")
    assert any("버전" in e for e in verify_bundle.verify(ver, tmp_path / "d" / "out"))
    (tmp_path / "e").mkdir()
    evil = make_bundle(tmp_path / "e", {"../escape.txt": "x", "version.txt": "v1\n"})
    assert "위험한 경로" in verify_bundle.verify(evil, tmp_path / "e" / "out")[0]


def test_diff_lists_explain_every_difference():
    p = ROOT / "reports/phase14_3_diff_lists.csv"
    if not p.exists():
        pytest.skip("차이 목록 없음")
    import pandas as pd
    d = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    held = d[d.list == "dart_held_373_vs_371"]
    ent = d[d.list == "entities_5468_vs_5463"]
    assert len(held) == 2 and set(held.id) == {"01222867", "01921199"} and (held.reason != "").all()              # 373 - 371
    assert len(ent) == 5 and ent.id.is_unique and (ent.reason != "").all()                                         # 5,468 - 5,463


def test_held_dart_value_is_not_shown_anywhere_on_result_page_source():
    """DART 급여가 품질 문제로 보류된 기업(level != ok)의 공시 값은 비교 그래프·사실표에도 쓰지 않는다(대표값 선택과 같은 기준)."""
    s = (ROOT / "web/js/corp.js").read_text(encoding="utf-8")
    assert "const pair = (dartOk && n.est != null)" in s
    assert "d.avg" not in s and "dartOk ? `${fmtMan(dv)}" in s                                                     # 모든 공시 숫자는 visibleDartAvg 를 거친 dv


def test_release_guard_decision_and_zip_inspection(tmp_path):
    import release_guard as rg
    assert rg.decide(False, False, False)[0] is True
    assert rg.decide(True, False, True)[0] is True                                                                # 권한 확인됨
    assert rg.decide(True, True, False)[0] is True                                                                # 비공개 저장소 보관만(배포는 별도 차단)
    ok, msg = rg.decide(True, False, False)
    assert ok is False and "차단" in msg                                                                          # 공개 저장소 + 권한 미확인
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("index.html", "x"); zf.writestr("data/pay/s/0.json", "{}")
    assert rg.bundle_has_saramin(z) is True
    z2 = tmp_path / "b.zip"
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("index.html", "x"); zf.writestr("data/finder/sm_entities.json", "[]")
    assert rg.bundle_has_saramin(z2) is True
    z3 = tmp_path / "c.zip"
    with zipfile.ZipFile(z3, "w") as zf:
        zf.writestr("index.html", "x"); zf.writestr("data/corp/1.json", "{}")
    assert rg.bundle_has_saramin(z3) is False


def test_release_guard_cli_ignores_a_false_manifest_and_blocks_public_unconfirmed(tmp_path):
    import release_guard as rg
    b = tmp_path / "bundle"
    b.mkdir()
    z = b / "pay-watch-site-x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("data/pay/s/1.json", "{}")
    (b / "manifest.json").write_text(json.dumps({"zip": z.name, "saramin_included": False}), encoding="utf-8")        # manifest 가 거짓이어도 zip 내용으로 판정
    assert rg.main([str(b), "--repo-private", "false", "--permitted", "false"]) == 2
    assert rg.main([str(b), "--repo-private", "true", "--permitted", "false"]) == 0
    assert rg.main([str(b), "--repo-private", "false", "--permitted", "true"]) == 0


def test_synthetic_test_bundle_passes_the_whole_pipeline_without_touching_the_real_site(tmp_path):
    """가상 소형 번들로 번들 검증→사람인 직접 검사→공개 검사→링크 점검을 로컬에서 재현한다. 실제 site/ 는 읽지도 쓰지도 않는다."""
    import make_test_bundle
    import subprocess
    import os
    real_version = (ROOT / "site/version.txt").read_text(encoding="utf-8") if (ROOT / "site/version.txt").exists() else None
    z = make_test_bundle.make(tmp_path / "dist-test")
    m = json.loads((tmp_path / "dist-test/manifest.json").read_text(encoding="utf-8"))
    assert m["test_bundle"] is True and m["saramin_included"] is False and z.stat().st_size < 20000                 # 소형, 테스트 표시
    site = tmp_path / "site"
    assert verify_bundle.verify(tmp_path / "dist-test", site) == []
    assert not package_site.saramin_present(site)                                                                   # 사람인 파일 없음
    env = {**os.environ, "PAYWATCH_SITE_DIR": str(site), "PAYWATCH_POLICY_MANIFEST": str(tmp_path / "dist-test/policy_manifest.json"), "PAYWATCH_SKIP_RAW_CHECK": "1"}
    py = [sys.executable, "-I", "-X", "utf8"]
    for script in ("check_public.py", "check_links.py"):
        r = subprocess.run(py + [str(ROOT / "pipeline" / script)], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, (script, r.stdout[-600:])
    text = "".join(p.read_text(encoding="utf-8") for p in site.rglob("*") if p.is_file() and p.suffix in (".json", ".html"))
    assert "TEST" in text and "삼성" not in text and "SK" not in text                                                # 실제 기업 데이터 없음
    assert (ROOT / "site/version.txt").read_text(encoding="utf-8") == real_version if real_version else True       # 실제 site/ 불변
