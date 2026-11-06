"""검증된 공개 산출물 번들 만들기(PHASE 14.3). site/(약 420MB)를 저장소 기록에 올리지 않고, 검사를 통과한 번들(zip + manifest.json)을 GitHub Release 자산으로 전달한다.
순서: ① check_public.py(연구용 혼입·정책·색인) 종료 코드 0 ② check_links.py 0 ③ **사람인 데이터 직접 검사**(파일이 있으면 config/publish.yaml 의 saramin_permission=confirmed 이고 config/saramin_permission_evidence.md 근거 파일이 있어야 함)
        ④ zip 생성 + manifest.json(버전·파일 수·바이트·sha256·사람인 포함 여부). 하나라도 실패하면 번들을 만들지 않는다.
--dry-run: 검사만 하고 번들은 만들지 않는다. 종료 코드: 0 성공, 1 검사 실패, 2 사람인 권한 미확인으로 차단.
실행: python -I -X utf8 pipeline/package_site.py [--dry-run] [--site-dir 경로] [--out 폴더]"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-I", "-X", "utf8"]
EVIDENCE = ROOT / "config/saramin_permission_evidence.md"


def saramin_present(site: Path) -> bool:
    return (site / "data/pay").exists() or (site / "data/finder/sm_entities.json").exists()


def saramin_allowed(cfg_text: str, evidence: Path = EVIDENCE) -> bool:
    return bool(re.search(r"^saramin_permission:\s*confirmed", cfg_text, re.M)) and evidence.exists() and evidence.stat().st_size >= 100


def run(script: str, env: dict) -> int:
    return subprocess.run(PY + [str(ROOT / "pipeline" / script)], cwd=ROOT, env=env).returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--site-dir", default=str(ROOT / "site"))
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args(argv)
    site, out = Path(a.site_dir).resolve(), Path(a.out).resolve()
    env = {**os.environ, "PAYWATCH_SITE_DIR": str(site)}
    cfg_path = Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml"))
    cfg = cfg_path.read_text(encoding="utf-8")
    sm = saramin_present(site)
    if sm and not saramin_allowed(cfg):                                  # 직접 검사: 종료 코드와 별개로 파일 존재 여부를 본다
        print("차단: site/ 에 사람인 데이터가 있으나 saramin_permission=confirmed 와 근거 파일(config/saramin_permission_evidence.md)이 없음. 번들을 만들지 않는다.")
        return 2
    for script in ("check_public.py", "check_links.py"):
        rc = run(script, env)
        if rc == 2 and script == "check_public.py":
            print("차단: check_public 이 배포 차단(종료 코드 2)을 보고함.")
            return 2
        if rc:
            print(f"실패: {script} 종료 코드 {rc}. 번들을 만들지 않는다.")
            return 1
    files = sorted(p for p in site.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in files)
    version = (site / "version.txt").read_text(encoding="utf-8").strip() if (site / "version.txt").exists() else "unknown"
    print(f"검사 통과: 파일 {len(files):,}개, {total / 1e6:.0f}MB, 버전 {version}, 사람인 포함 {sm}")
    if a.dry_run:
        print("--dry-run: 번들은 만들지 않았다.")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    zpath = out / f"pay-watch-site-{version}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, p.relative_to(site).as_posix())
    h = hashlib.sha256(zpath.read_bytes()).hexdigest()
    manifest = {"version": version, "zip": zpath.name, "zip_sha256": h, "files": len(files), "bytes": total, "saramin_included": sm, "test_bundle": False,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "checks": ["check_public", "check_links", "saramin_direct_inspection"]}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"번들 생성: {zpath} ({zpath.stat().st_size / 1e6:.0f}MB) sha256={h[:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
