"""web/ 정적 파일을 site/ 로 복사(site/data 는 건드리지 않음). 배포물에는 원시 데이터·키가 들어가지 않는다.
캐시 무효화: 정적 파일(js/css/html)의 내용 해시를 모든 로컬 스크립트·스타일·모듈 import 에 ?v= 로 붙인다.
(브라우저/CDN 이 새 corp.js 와 옛 common.js 를 섞어 쓰는 문제를 막는다.)"""
import hashlib
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC, DST = ROOT / "web", ROOT / "site"
VENDOR = "vendor"


def content_hash(files) -> str:
    h = hashlib.sha1()
    for p in sorted(files):
        h.update(str(p.relative_to(SRC)).encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()[:10]


def version_text(text: str, v: str, kind: str) -> str:
    if kind == "html":
        return re.sub(r'((?:src|href)="(?:js|css)/[^"?]+\.(?:js|css))"', rf'\1?v={v}"', text)
    # js: 같은 폴더 모듈 import (./xxx.js) 에 버전 부여
    return re.sub(r'(from\s+"\./[A-Za-z0-9_\-]+\.js)"', rf'\1?v={v}"', text)


def main():
    files = [p for p in SRC.rglob("*") if p.is_file()]
    v = content_hash([p for p in files if VENDOR not in p.parts])
    for p in files:
        t = DST / p.relative_to(SRC)
        t.parent.mkdir(parents=True, exist_ok=True)
        if VENDOR not in p.parts and p.suffix in (".html", ".js"):
            t.write_text(version_text(p.read_text(encoding="utf-8"), v, p.suffix[1:]), encoding="utf-8")
        else:
            shutil.copy2(p, t)
    (DST / "version.txt").write_text(v + "\n", encoding="utf-8")
    print("site 갱신:", sum(1 for _ in DST.rglob("*.html")), "html, 버전", v)


if __name__ == "__main__":
    main()
