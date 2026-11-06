"""저장소 보호 장치(PHASE 14.3). GitHub 공개 저장소에 올라가면 안 되는 파일이 '커밋 대상'에 들어 있으면 실패한다.
- 대상: .gitignore 에 걸리지 않는 모든 파일(Git 저장소면 git ls-files, 아니면 폴더를 훑어 .gitignore 규칙으로 걸러낸다).
- 금지: 생성된 공개 산출물 site/·preview/·dist/ 전체(공개 데이터는 저장소 기록에 누적하지 않고 검증된 번들로 전달한다), 사람인 데이터·통합 데이터셋·내부 매칭/선택 감사 파일, 원자료(data/raw·interim·processed), .env, 대용량(25MB 초과) 파일.
- 사람인 관련 '코드·문서'(web/js/saramin.js, pipeline/build_saramin.py 등)는 허용한다. 데이터 파일만 막는다.
- 이 검사는 테스트 종료 코드와 별개로 파일 자체를 직접 본다. CI(pages.yml)와 로컬(pre-commit 용)에서 같은 스크립트를 쓴다.
실행: python -I -X utf8 pipeline/guard_repo.py [루트]   (종료 코드 0=통과, 1=금지 파일 있음)"""
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 25 * 1024 * 1024
FORBIDDEN_PREFIX = ("site/", "preview/", "dist/", "dist-test/", "data/raw/", "data/interim/", "data/processed/")
FORBIDDEN_NAME = re.compile(r"(^|/)(\.env|paywatch_integrated[^/]*|saramin_all_enterprises[^/]*|saramin_sample[^/]*|unverified_isolated[^/]*|checkpoint_page_[^/]*|sm_entities\.json)$")
FORBIDDEN_PATH = re.compile(r"(^|/)reports/phase14_2_[^/]*$|(^|/)data/pay/")
DATA_EXT = (".csv", ".json", ".parquet", ".xlsx", ".zip")
SARAMIN_DATA = re.compile(r"saramin|사람인", re.I)


def ignore_rules(root: Path) -> list[str]:
    f = root / ".gitignore"
    return [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")] if f.exists() else []


def ignored(rel: str, rules: list[str]) -> bool:
    for r in rules:
        r = r.rstrip("/") if r.endswith("/") else r
        if r.endswith("/") or "/" not in r.strip("/"):
            pat = r.strip("/")
            if rel == pat or rel.startswith(pat + "/") or any(fnmatch.fnmatch(part, pat) for part in rel.split("/")):
                return True
        if fnmatch.fnmatch(rel, r.lstrip("/")) or rel.startswith(r.strip("/") + "/"):
            return True
    return False


def candidate_files(root: Path) -> list[str]:
    if (root / ".git").exists():
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, capture_output=True, text=True, encoding="utf-8")
        return [p for p in out.stdout.split("\0") if p]
    rules = ignore_rules(root)
    files = []
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if not ignored(rel, rules):
                files.append(rel)
    return files


def check(root: Path = ROOT) -> list[str]:
    bad = []
    for rel in candidate_files(root):
        p = root / rel
        if rel.startswith(FORBIDDEN_PREFIX) or FORBIDDEN_NAME.search(rel) or FORBIDDEN_PATH.search(rel):
            bad.append(f"{rel}: 공개 저장소에 올리면 안 되는 파일(생성 산출물·원자료·사람인/통합 데이터·내부 감사)")
        elif p.suffix.lower() in DATA_EXT and SARAMIN_DATA.search(rel) and not rel.startswith(("tests/", "docs/", "config/")):
            bad.append(f"{rel}: 사람인 이름이 들어간 데이터 파일")
        elif p.exists() and p.stat().st_size > MAX_BYTES:
            bad.append(f"{rel}: 25MB 초과 대용량 파일({p.stat().st_size / 1e6:.0f}MB)")
    return bad


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    bad = check(root)
    print(f"저장소 보호 검사: 실패 {len(bad)}건")
    for b in bad[:30]:
        print(" -", b)
    sys.exit(1 if bad else 0)
