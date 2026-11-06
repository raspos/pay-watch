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

SITE, PREV, EXP = ROOT / "site", ROOT / "preview", ROOT / "web_exp"
ALLOWED_EXT = {".html", ".js", ".css"}                                                 # web_exp 에는 코드만 둔다(데이터 파일 금지)


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode("utf-8")); h.update(p.read_bytes())
    return h.hexdigest()


def exp_files():
    files = [p for p in EXP.rglob("*") if p.is_file()]
    bad = [p for p in files if p.suffix not in ALLOWED_EXT]
    if bad:
        raise SystemExit(f"web_exp/ 에는 코드(html/js/css)만 둘 수 있습니다: {bad}")
    return files


def main():
    if not (SITE / "version.txt").exists():
        raise SystemExit("먼저 python pipeline/build_site.py 로 site/ 를 만드세요")
    before = tree_hash(SITE)
    if PREV.exists():
        assert PREV.resolve() == ROOT / "preview"
        shutil.rmtree(PREV)
    shutil.copytree(SITE, PREV)
    site_v = (SITE / "version.txt").read_text(encoding="utf-8").strip()
    files = exp_files()
    h = hashlib.sha1()
    for p in sorted(files):
        h.update(str(p.relative_to(EXP)).encode("utf-8")); h.update(p.read_bytes())
    ev = h.hexdigest()[:10]
    for p in files:
        t = PREV / p.relative_to(EXP); t.parent.mkdir(parents=True, exist_ok=True)
        txt = p.read_text(encoding="utf-8")
        if p.suffix == ".html":
            txt = re.sub(r'((?:src|href)="(?:js|css)/[^"?]+\.(?:js|css))"', rf'\1?v={ev}"', txt)
        elif p.suffix == ".js":
            txt = txt.replace('from "./common.js"', f'from "./common.js?v={site_v}"')          # 사이트의 common.js 와 같은 모듈 인스턴스를 쓴다
            txt = re.sub(r'(from\s+"\./exp-[A-Za-z0-9_\-]+\.js)"', rf'\1?v={ev}"', txt)
        t.write_text(txt, encoding="utf-8")
    for page in ("index.html", "company.html"):                                            # 연구용 영역을 같은 결과 화면에 덧붙이는 로더(공개 site/ 의 파일은 건드리지 않고 preview/ 복사본만 수정)
        f = PREV / page; t = f.read_text(encoding="utf-8")
        if "</body>" not in t:
            raise SystemExit(f"{page} 형식이 바뀌었습니다")
        t = t.replace("</head>", f'<link rel="stylesheet" href="css/exp.css?v={ev}"></head>', 1)
        f.write_text(t.replace("</body>", f'<script type="module" src="js/exp-embed.js?v={ev}"></script></body>', 1), encoding="utf-8")
    meta = export_exp.export(PREV / "data/exp")
    (PREV / "PREVIEW_ONLY_NOT_FOR_PUBLIC.txt").write_text("로컬 미리보기 전용(실험적 추정 포함). PHASE 12 전까지 배포 금지.\n", encoding="utf-8")
    assert tree_hash(SITE) == before, "build_preview 가 site/ 를 변경했습니다"
    print("preview 빌드 완료:", meta, "| site/ 변경 없음 확인, 실험 버전", ev)
    print("로컬 확인: python -I -X utf8 pipeline/serve_preview.py  → http://127.0.0.1:8791/ (127.0.0.1 에서만 열림. python -m http.server 는 모든 인터페이스에 열리므로 쓰지 않는다)")


if __name__ == "__main__":
    main()
