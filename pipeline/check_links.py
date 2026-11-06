"""배포 전 링크·경로 점검(site/ 정적 점검, 서버 불필요).
- HTML 의 로컬 href/src 와 JS 의 모듈 import 가 실제 파일을 가리킨다.
- JS 가 내부 페이지로 보내는 주소(`x.html?...`)의 페이지가 있다.
- JS 가 읽는 데이터 파일(getJSON 문자열 리터럴)이 data/ 에 있다.
- 통합 검색 색인의 모든 기업이 결과 화면(company.html?corp=코드)으로 연결되고, 상세 페이지가 있다고 표시된 기업은 법인 샤드에 실제로 있다.
- 첫 화면 로딩량(HTML+CSS+JS+검색 색인)을 보고한다.
실행: python -I -X utf8 pipeline/check_links.py"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("PAYWATCH_SITE_DIR", ROOT / "site"))      # 번들 검증용 경로(기본은 site/)


def main() -> int:
    fails: list[str] = []
    for h in SITE.glob("*.html"):
        t = h.read_text(encoding="utf-8")
        for m in re.finditer(r"""(?:href|src)="(/[^/"][^"]*)"|fetch\(\s*["'`](/[^/][^"'`]*)|url\(\s*["']?(/[^/)"']+)|location\.href\s*=\s*["'`](/[^/][^"'`]*)""", t):
            u = m.group(1).split("?")[0]
            if re.match(r"^(https?:|mailto:|data:|//)", u):
                continue
            if not (SITE / u).exists():
                fails.append(f"{h.name}: 없는 파일 {u}")
    for j in SITE.rglob("js/*.js"):
        if "vendor" in j.parts:
            continue
        t = j.read_text(encoding="utf-8")
        for m in re.finditer(r'from\s+"(\./[^"?]+)', t):
            if not (j.parent / m.group(1)).exists():
                fails.append(f"{j.name}: 없는 모듈 {m.group(1)}")
        for m in re.finditer(r'["`\'(]((?:index|company|compare|lab|methodology)\.html)(?:[?"`\')])', t):
            if not (SITE / m.group(1)).exists():
                fails.append(f"{j.name}: 없는 페이지 {m.group(1)}")
        for m in re.finditer(r'getJSON\(\s*["\']([^"\'$`]+\.json)["\']', t):
            if not (SITE / "data" / m.group(1)).exists():
                fails.append(f"{j.name}: 없는 데이터 {m.group(1)}")
    # GitHub Pages 저장소 하위 경로(user.github.io/<repo>/)에서도 동작하려면 루트 절대 경로(/…)를 쓰지 않는다
    for f in list(SITE.glob("*.html")) + [p for p in SITE.glob("js/*.js")] + [SITE / "css/style.css"]:
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"""(?:href|src)="(/[^/"][^"]*)"|fetch\(\s*["'`](/[^/][^"'`]*)|url\(\s*["']?(/[^/)"']+)|location\.href\s*=\s*["'`](/[^/][^"'`]*)""", t):
            fails.append(f"{f.name}: 루트 절대 경로 {next(g for g in m.groups() if g)}")
    rows = json.loads((SITE / "data/finder/entities.json").read_text(encoding="utf-8"))
    shard_codes: set[str] = set()
    for p in (SITE / "data/corp").glob("*.json"):
        shard_codes |= set(json.loads(p.read_text(encoding="utf-8")).keys())
    bad_page = [r[0] for r in rows if (r[4] & 1) != (1 if r[0] in shard_codes else 0)]
    if bad_page:
        fails.append(f"상세 페이지 표시와 법인 샤드가 다름 {len(bad_page)}곳 예 {bad_page[:3]}")
    import gzip
    gz = lambda fs: sum(len(gzip.compress((SITE / f).read_bytes(), 6)) for f in fs if (SITE / f).exists())
    init = ["index.html", "css/style.css", "js/home.js", "js/common.js", "js/finder-ui.js", "js/finder-core.js", "js/search.js", "js/site-config.js", "js/vendor/fuse.min.js"]
    lazy = ["data/finder/entities.json", "data/index/top.json", "data/index/ranges.json"]
    print(f"링크 점검: 실패 {len(fails)}건 · 색인 기업 {len(rows):,}곳 · 첫 화면 필수 {gz(init) / 1024:.0f}KB(gzip) · 검색 시작 시 추가 {gz(lazy[:1]) / 1024:.0f}KB(회사 색인)+{gz(lazy[1:]) / 1024:.0f}KB(국민연금 사업장 색인)")
    for f in fails[:30]:
        print(" -", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
