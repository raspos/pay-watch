"""파이프라인 검증용 소형 테스트 번들 생성(PHASE 14.3). 실제 기업 데이터가 없는 가상의 사이트(수 KB)를 zip + manifest.json + policy_manifest.json 으로 만든다.
- manifest.json 의 test_bundle=true: pages.yml 은 테스트 번들을 **Pages 에 배포하지 않고**(실제 공개 사이트를 덮어쓰지 않음) 검증만 한 뒤 점검용 Actions 아티팩트로만 남긴다.
- 가상 기업: 'TEST' 접두의 이름과 99999xxx 번호만 사용. 실제 기업·급여 값 없음. 사람인 파일 없음.
실행: python -I -X utf8 pipeline/make_test_bundle.py [--out 폴더]   → <폴더>/pay-watch-site-test-<해시>.zip, manifest.json, policy_manifest.json"""
import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("index", "company", "compare", "lab", "methodology")
CODE = "99999901"


def build_site(site: Path) -> None:
    (site / "css").mkdir(parents=True)
    (site / "css/style.css").write_text("body{margin:0}\n", encoding="utf-8")
    for p in PAGES:
        (site / f"{p}.html").write_text(f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>테스트 번들 {p}</title><link rel="stylesheet" href="css/style.css"></head><body><p>파이프라인 검증용 가상 사이트입니다.</p></body></html>\n', encoding="utf-8")
    (site / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (site / "data/finder").mkdir(parents=True)
    (site / "data/corp").mkdir(parents=True)
    rows = [[CODE, "TEST 가상기업(주)", "TEST 가상기업", "", 1 | 2 | 4, 10]]                        # 상세 있음·공시 있음·국민연금 있음(모두 가상)
    (site / "data/finder/entities.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (site / "data/finder/dart_only.json").write_text("{}", encoding="utf-8")
    shard = {CODE: {"code": CODE, "n": "TEST 가상기업(주)", "dart": {"avg": 50000000, "level": "ok", "fy": 2025, "employees": 10, "tenure": 3.0}, "nps": {"est": 1}}}
    (site / f"data/corp/{int(CODE) % 128}.json").write_text(json.dumps(shard, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def make(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        site = Path(t) / "site"
        build_site(site)
        files = sorted(p for p in site.rglob("*") if p.is_file())
        version = "test-" + hashlib.sha1(b"".join(p.read_bytes() for p in files)).hexdigest()[:8]
        (site / "version.txt").write_text(version + "\n", encoding="utf-8")
        files = sorted(p for p in site.rglob("*") if p.is_file())
        z = out / f"pay-watch-site-{version}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in files:
                zf.write(p, p.relative_to(site).as_posix())
        manifest = {"version": version, "zip": z.name, "zip_sha256": hashlib.sha256(z.read_bytes()).hexdigest(), "files": len(files), "bytes": sum(p.stat().st_size for p in files),
                    "saramin_included": False, "test_bundle": True, "built_at": "synthetic", "checks": []}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "policy_manifest.json").write_text(json.dumps({"tenure_max": 45.0, "doubt": [], "held": [], "restored": [], "dart_only": 0}), encoding="utf-8")
    return z


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist-test"))
    print(make(Path(ap.parse_args().out)))
