"""Release 업로드 전 필수 검증과 업로드(예방 통제). GitHub 에 번들을 올리는 유일한 지원 경로다 — 사후 자동 삭제(release-guard.yml)는 보조 장치일 뿐 이 검증을 대신하지 않는다.
검증(모두 통과해야 업로드): ① manifest·zip 존재와 sha256 일치 ② zip 안의 파일 이름을 직접 검사해 사람인 데이터 포함 여부 판정(manifest 표시는 믿지 않고, 표시와 다르면 차단)
 ③ 사람인이 포함되면: 게시·재배포 권한 확인(publish.yaml + 근거 파일)일 때만 허용. 권한 미확인이면 비공개 저장소에서만 보관 허용하고, 저장소가 공개이거나 공개 여부를 확인할 수 없으면(fail-closed) 차단
 ④ 실제 번들은 package_site.py 의 검사 기록(check_public·check_links)이 manifest 에 있어야 함. 테스트 번들(manifest.test_bundle=true, 가상 데이터)은 권한 미확인 상태에서도 허용
기본은 점검만(dry-run). --execute 일 때만 manifest.json 에 업로드 전 검증 표시(preupload)를 기록하고 `gh release create` 로 올린다(gh 필요). 실제 번들은 이 표시가 없으면 pages.yml 이 배포를 거부한다.
종료 코드: 0 통과(또는 업로드 완료), 1 일반 실패, 2 사람인 권한 문제로 차단.
실행: python -I -X utf8 pipeline/publish_release.py <번들폴더> --repo 소유자/저장소 --tag 태그 [--repo-private auto|true|false] [--execute] [--draft]"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import package_site  # noqa: E402
import release_guard  # noqa: E402

REQUIRED_CHECKS = {"check_public", "check_links"}


def repo_visibility(repo: str, runner=subprocess.run) -> bool | None:
    """True=비공개, False=공개, None=확인 불가(gh 없음·권한 없음 등)."""
    if not shutil.which("gh") and runner is subprocess.run:
        return None
    try:
        r = runner(["gh", "repo", "view", repo, "--json", "isPrivate", "--jq", ".isPrivate"], capture_output=True, text=True, encoding="utf-8", timeout=60)
        out = (r.stdout or "").strip().lower()
        return True if out == "true" else False if out == "false" else None
    except Exception:
        return None


def evaluate(bundle_dir: Path, repo_private: bool | None, permitted: bool) -> tuple[bool, int, list[str], dict]:
    """반환: (통과, 종료 코드, 사유 목록, 정보). repo_private None 은 확인 불가."""
    problems: list[str] = []
    info: dict = {}
    mp = bundle_dir / "manifest.json"
    if not mp.exists():
        return False, 1, ["manifest.json 없음"], info
    m = json.loads(mp.read_text(encoding="utf-8"))
    z = bundle_dir / m.get("zip", "")
    if not z.exists():
        return False, 1, [f"zip 없음: {m.get('zip')}"], info
    if hashlib.sha256(z.read_bytes()).hexdigest() != m.get("zip_sha256"):
        return False, 1, ["sha256 불일치: 번들이 변조되었거나 손상됨"], info
    test = bool(m.get("test_bundle"))
    has = release_guard.bundle_has_saramin(z)
    info.update(test_bundle=test, saramin_in_zip=has)
    if has != bool(m.get("saramin_included")):
        return False, 2 if has else 1, ["manifest 의 saramin_included 가 zip 내용과 다름(zip 내용을 기준으로 차단)"], info
    if not test and not REQUIRED_CHECKS <= set(m.get("checks", [])):
        problems.append("package_site.py 검사 기록(check_public·check_links)이 manifest 에 없음: 검증 없이 만든 번들")
    if has and not permitted:
        if repo_private is True:
            info["gate"] = "private_storage"                           # 권한 미확인: 비공개 저장소 보관만(Pages 배포는 별도로 차단)
        else:
            why = "저장소가 공개" if repo_private is False else "저장소 공개 여부를 확인할 수 없음(fail-closed)"
            return False, 2, [f"차단: 사람인 데이터가 든 번들을 올릴 수 없음 — 게시·재배포 권한 미확인, {why}"] + problems, info
    else:
        info["gate"] = "permitted" if has else ("test" if test else "clean")
    return (not problems), (1 if problems else 0), problems, info


def stamp(bundle_dir: Path, info: dict, repo: str, repo_private: bool | None) -> None:
    mp = bundle_dir / "manifest.json"
    m = json.loads(mp.read_text(encoding="utf-8"))
    m["preupload"] = {"checked": True, "gate": info.get("gate"), "repo": repo, "repo_private": repo_private, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None, runner=subprocess.run) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle_dir")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--repo-private", default="auto", choices=["auto", "true", "false"])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args(argv)
    b = Path(a.bundle_dir)
    cfg_path = Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml"))
    permitted = package_site.saramin_allowed(cfg_path.read_text(encoding="utf-8"))
    priv = repo_visibility(a.repo, runner) if a.repo_private == "auto" else (a.repo_private == "true")
    ok, code, problems, info = evaluate(b, priv, permitted)
    print(f"업로드 전 검증: {'통과' if ok else '실패'} · 저장소 비공개={priv} · 권한 확인={permitted} · {info}")
    for p in problems:
        print(" -", p)
    if not ok:
        return code
    if not a.execute:
        print("점검만 수행했다(dry-run). 올리려면 --execute 를 붙인다.")
        return 0
    if runner is subprocess.run and not shutil.which("gh"):
        print("gh CLI 가 없어 업로드할 수 없다. 검증은 통과했으나 업로드하지 않았다.")
        return 1
    stamp(b, info, a.repo, priv)
    m = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    files = [str(b / m["zip"]), str(b / "manifest.json")] + ([str(b / "policy_manifest.json")] if (b / "policy_manifest.json").exists() else [])
    cmd = ["gh", "release", "create", a.tag, *files, "--repo", a.repo, "--title", f"PAY워치 번들 {m['version']}", "--notes", "업로드 전 검증(publish_release.py)을 통과한 번들"] + (["--draft"] if a.draft else [])
    r = runner(cmd)
    return getattr(r, "returncode", 0) or 0


if __name__ == "__main__":
    sys.exit(main())
