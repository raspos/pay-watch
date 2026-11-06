"""배포 직전 번들 검증(CI 에서 사용). manifest.json 의 sha256 과 zip 이 같은지 확인하고 지정 폴더(site/)에 푼 뒤 파일 수·버전을 manifest 와 대조한다.
하나라도 다르면 종료 코드 1. 실행: python -I -X utf8 pipeline/verify_bundle.py <번들폴더> <풀 폴더>"""
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def verify(bundle_dir: Path, dest: Path) -> list[str]:
    errs = []
    m = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    z = bundle_dir / m["zip"]
    if not z.exists():
        return [f"zip 없음: {m['zip']}"]
    h = hashlib.sha256(z.read_bytes()).hexdigest()
    if h != m["zip_sha256"]:
        return ["sha256 불일치: 번들이 변조되었거나 손상됨"]
    with zipfile.ZipFile(z) as zf:
        bad = zf.testzip()
        if bad:
            errs.append(f"손상된 항목: {bad}")
        if any(n.startswith(("/", "..")) or ".." in n.split("/") for n in zf.namelist()):
            return ["zip 안에 위험한 경로가 있음"]
        zf.extractall(dest)
    n = sum(1 for p in dest.rglob("*") if p.is_file())
    if n != m["files"]:
        errs.append(f"파일 수 불일치: manifest {m['files']} / 실제 {n}")
    v = (dest / "version.txt").read_text(encoding="utf-8").strip() if (dest / "version.txt").exists() else "unknown"
    if v != m["version"]:
        errs.append(f"버전 불일치: manifest {m['version']} / 실제 {v}")
    return errs


if __name__ == "__main__":
    e = verify(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"번들 검증: 실패 {len(e)}건")
    for x in e:
        print(" -", x)
    sys.exit(1 if e else 0)
