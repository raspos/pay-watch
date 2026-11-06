"""PAY RANK 공개 데이터(rank.json) 검증: 대표값 규칙과 같은 출처, 보류된 공시값 미사용, 업종은 검증된 분류만, 최소 필드, 공개 검사 규칙."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
F = SITE / "data/rank/rank.json"
pytestmark = pytest.mark.skipif(not F.exists(), reason="PAY RANK 데이터 없음(CI)")


def rank():
    return json.loads(F.read_text(encoding="utf-8"))


def corp():
    out = {}
    for p in (SITE / "data/corp").glob("*.json"):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


def test_rank_rows_follow_representative_rules_and_counts():
    d = rank()
    assert set(d) == {"v", "inds", "rows"} and len(d["rows"]) == 4000
    assert sum(r[3] == 0 for r in d["rows"]) == 2071 and sum(r[3] == 1 for r in d["rows"]) == 1929
    assert len({r[0] for r in d["rows"]}) == 4000 and all(len(r) == 7 and r[2] > 0 for r in d["rows"])
    assert all(a[2] >= b[2] for a, b in zip(d["rows"], d["rows"][1:]))                      # 연봉 내림차순
    only = json.loads((SITE / "data/finder/dart_only.json").read_text(encoding="utf-8"))
    c = corp()
    for r in d["rows"]:
        if r[3] == 0:                                                                       # DART 값은 유효(level=ok)한 것만, 값도 같다
            dart = (c.get(r[0]) or {}).get("dart") or only.get(r[0])
            assert dart and dart.get("level") == "ok" and dart["avg"] == r[2], r[0]


def test_held_dart_pay_is_never_in_rank_data():
    c = corp()
    held = {code for code, r in c.items() if r.get("hold") or (r.get("dart") and r["dart"].get("level") != "ok")}
    assert len(held) >= 300
    rows = {r[0]: r for r in rank()["rows"]}
    assert all(h not in rows or rows[h][3] == 1 for h in held)                              # 보류 기업은 DART 출처 행이 없다(사람인 추정이 있을 때만 사람인 행)
    assert not any(r[3] == 0 for h in held for r in [rows.get(h)] if r)


def test_industry_only_for_dart_firms_with_verified_classification_and_flags():
    d = rank()
    assert len(d["inds"]) == 60 and all(isinstance(n, str) and n for n in d["inds"])
    with_ind = [r for r in d["rows"] if r[5] >= 0]
    assert 1500 < len(with_ind) < 2600 and all(re.fullmatch(r"\d{8}", r[0]) for r in with_ind)   # 사람인 전용은 분류 없음(-1)
    assert all(r[5] == -1 for r in d["rows"] if r[0].startswith("S"))
    assert sum(r[6] for r in d["rows"]) > 50 and any(r[6] for r in d["rows"] if "지주" in r[1] or "홀딩스" in r[1])


def test_public_check_validates_rank_file(tmp_path):
    src = (ROOT / "pipeline/check_public.py").read_text(encoding="utf-8")
    assert "def check_rank" in src and "보류" in src
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(ROOT / "pipeline/check_public.py")], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       env={**__import__("os").environ, "PAYWATCH_SKIP_RAW_CHECK": "1"})
    assert "실패 0건" in r.stdout and r.returncode == 0, r.stdout[-400:]


def test_rank_page_is_linked_and_keeps_existing_features():
    nav = (SITE / "js/common.js").read_text(encoding="utf-8")
    assert '"rank.html"' in nav and '["lab.html", "LAB"]' in nav and '"compare.html"' in nav
    corp_js = (SITE / "js/corp.js").read_text(encoding="utf-8")
    assert "rank.html?add=" in corp_js and "compare.html?items=" in corp_js                 # 비교 버튼과 기존 버튼 모두 유지
    assert "est-embed" in (SITE / "company.html").read_text(encoding="utf-8")                  # 근속 구간별 추정 영역 유지
    html = (SITE / "rank.html").read_text(encoding="utf-8")
    assert "내 친구들 연봉 랭킹" in html and "우리 중 누가 제일 잘 버는 회사에 다닐까?" in html and "친구 개인의 연봉이 아닌 재직 회사의 평균연봉 기준입니다." in html
