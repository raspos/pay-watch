"""연구용 미리보기 빌드(로컬 전용). 공개 빌드(build_site.py → site/)와 완전히 분리한다.
- site/ 를 preview/ 로 복사한 뒤 web_exp/(코드만)와 실험 데이터(preview/data/exp/)를 덧입힌다. site/ 의 파일은 읽기만 하며, 끝에서 해시로 변경 여부를 검증한다.
- 연구용 영역은 별도 검색창이 아니라 같은 결과 화면(company.html?corp=코드)에 덧붙는다. preview/ 의 index.html·company.html 복사본에만 로더 한 줄을 추가한다(공개용 web/·site/ 는 그대로).
- preview/ 는 .gitignore 대상이며 PHASE 12 통합 검증 전까지 배포하지 않는다.
실행: python -I -X utf8 pipeline/build_preview.py   (먼저 pipeline/build_site.py 로 site/ 가 만들어져 있어야 한다)"""
import hashlib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import export_exp                                                                      # noqa: E402

SITE, PREV = ROOT / "site", ROOT / "preview"


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode("utf-8")); h.update(p.read_bytes())
    return h.hexdigest()


def main():
    if not (SITE / "version.txt").exists():
        raise SystemExit("먼저 python pipeline/build_site.py 로 site/ 를 만드세요")
    before = tree_hash(SITE)
    if PREV.exists():
        assert PREV.resolve() == ROOT / "preview"
        shutil.rmtree(PREV)
    shutil.copytree(SITE, PREV)
    # 근속 추정 영역(est-*.js)은 공개 사이트 코드로 이미 site/ 에 있다. 미리보기에는 연구 전용 전체 데이터(data/exp: 등급·상태·사유 포함)만 덧붙인다.
    meta = export_exp.export(PREV / "data/exp")
    (PREV / "PREVIEW_ONLY_NOT_FOR_PUBLIC.txt").write_text("로컬 미리보기 전용(실험적 추정 포함). PHASE 12 전까지 배포 금지.\n", encoding="utf-8")
    assert tree_hash(SITE) == before, "build_preview 가 site/ 를 변경했습니다"
    print("preview 빌드 완료:", meta, "| site/ 변경 없음 확인, 실험 버전", ev)
    print("로컬 확인: python -I -X utf8 pipeline/serve_preview.py  → http://127.0.0.1:8791/ (127.0.0.1 에서만 열림. python -m http.server 는 모든 인터페이스에 열리므로 쓰지 않는다)")


if __name__ == "__main__":
    main()
