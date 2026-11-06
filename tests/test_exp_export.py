"""PHASE 11 연구용 미리보기: 내보낸 JSON이 저장된 연구 결과(PHASE 10 CSV)와 일치하는지, DART 코드 무결성, 공개 빌드(site/) 분리를 검증한다."""
import glob
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
WM = ROOT / "reports/wage_model"
PREV = ROOT / "preview"
need = [WM / "phase12_ranges_rawprecision.csv", WM / "phase10_shape_estimates.csv", WM / "phase9_group_a_quality.csv", ROOT / "data/raw/dart/cache", ROOT / "pipeline/build_preview.py", ROOT / "web_exp/js/exp-section.js"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in need), reason="연구 산출물 없음")
BINS = ["1년미만", "1~3년미만", "3~5년미만", "5~10년미만", "10년이상"]


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode("utf-8")); h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def built():
    py = [sys.executable, "-I", "-X", "utf8"]
    subprocess.run(py + [str(ROOT / "pipeline/build_site.py")], check=True, cwd=ROOT, capture_output=True)
    before = tree_hash(ROOT / "site")
    subprocess.run(py + [str(ROOT / "pipeline/build_preview.py")], check=True, cwd=ROOT, capture_output=True)
    return before


@pytest.fixture(scope="module")
def recs(built):
    out = {}
    for p in glob.glob(str(PREV / "data/exp/f/*.json")):
        out.update(json.load(open(p, encoding="utf-8")))
    return out


def test_build_preview_does_not_modify_site(built):
    assert tree_hash(ROOT / "site") == built


def test_ids_are_8digit_strings_matching_dart_cache(recs):
    cache = {Path(p).name.split("_")[0] for p in glob.glob(str(ROOT / "data/raw/dart/cache/empSttus/*_2025_11011.json"))}
    # PHASE 13: 연구용 색인은 DART 캐시 3,912곳 전체(A그룹 2,320 + 자료 부족 D 1,592). A그룹이 아닌 기업은 이름·식별자·이유만 가진다.
    assert len(recs) == 3912 and all(len(c) == 8 and c.isdigit() for c in recs)
    assert set(recs) <= cache
    assert len({int(c) for c in recs}) == len(recs)                     # 정수 변환 충돌 없음
    idx = json.load(open(PREV / "data/exp/index.json", encoding="utf-8"))
    assert len(idx) == 3912 and len({r[0] for r in idx}) == 3912 and {r[0] for r in idx} == set(recs)
    for r in idx:                                                         # 색인 항목이 상세 샤드와 같은 기업을 가리킨다
        assert recs[r[0]]["n"] == r[1]
    for c, r in recs.items():                                             # 샤드 위치 규칙
        assert (PREV / "data/exp/f" / f"{int(c) % 64}.json").exists()
    Q = pd.read_csv(WM / "phase9_group_a_quality.csv", encoding="utf-8-sig", dtype={"corp_code": str}); Q = Q[Q.A그룹 == True]      # noqa: E712
    assert dict(zip(Q.corp_code, Q.기업명)) == {c: r["n"] for c, r in recs.items() if r["s"] is not None}      # A그룹 2,320곳은 기존과 동일
    assert sum(r["s"] is not None for r in recs.values()) == 2320


def test_values_match_stored_rawprecision_results_exactly(recs):
    E = pd.read_csv(WM / "phase12_ranges_rawprecision.csv", encoding="utf-8-sig", dtype={"corp_code": str}); E["corp_code"] = E.corp_code.str.zfill(8)
    checked = 0
    for code, g in E.groupby("corp_code"):
        r = recs[code]; g = g.set_index("구간")
        if r["g"] in ("C", "D"):                                                          # 등급 C·D 는 범위를 데이터에 싣지 않는다(JS 에서 가리는 것이 아님)
            assert r["b"] is None and r["x"] is None, code
            checked += 1; continue
        assert r["b"] == [[int(g.loc[b, "[기존] 하한_만원"]), int(g.loc[b, "[기존] 상한_만원"])] for b in BINS], code
        if g["형태실험"].iloc[0] == "실행":
            assert r["x"] == [[int(g.loc[b, "[신규] 하한_만원"]), int(g.loc[b, "[신규] 상한_만원"])] for b in BINS] and r["h"] is False
            assert all(x[0] <= b[0] and x[1] >= b[1] for x, b in zip(r["x"], r["b"]))      # 확대 범위는 기본 범위를 포함
        else:
            assert r["x"] is None and r["h"] is True                                       # 보류: 기본 범위를 복제하지 않는다
        checked += 1
    assert checked == 2301


def test_web_values_close_to_phase10_except_known_rounding_case(recs):
    grades = {c: r["g"] for c, r in recs.items()}
    E = pd.read_csv(WM / "phase10_shape_estimates.csv", encoding="utf-8-sig", dtype={"corp_code": str}); E["corp_code"] = E.corp_code.str.zfill(8)
    far = set()
    for code, g in E.groupby("corp_code"):
        g = g.set_index("구간")
        if recs[code]["b"] is None: continue                                              # C·D 는 범위 없음
        for i, b in enumerate(BINS):
            lo, hi = recs[code]["b"][i]
            if abs(lo - g.loc[b, "[기존] 하한_만원"]) / g.loc[b, "[기존] 하한_만원"] > 0.005 or abs(hi - g.loc[b, "[기존] 상한_만원"]) / g.loc[b, "[기존] 상한_만원"] > 0.005: far.add(recs[code]["n"])
    assert far <= {"신풍제약(주)"}                                        # 평균근속 반올림이 m10 격자 경계 시나리오를 바꾼 유일한 기업(PHASE 12 감사)


def test_counts_held_and_not_estimated(recs):
    held = [r for r in recs.values() if r["h"]]; na = [r for r in recs.values() if r["s"] in ("INVALID", "INSUFFICIENT")]
    assert len(held) == 16 and all(r["b"] is not None and r["x"] is None and r["g"] == "B" for r in held)
    assert len(na) == 19 and all(r["b"] is None and r["x"] is None for r in na)
    ab = [r for r in recs.values() if r["g"] in ("A", "B")]
    assert len(ab) == 2138 and sum(r["x"] is not None for r in ab) == 2138 - 16 and all(r["b"] is not None for r in ab)
    assert sum(r["s"] in ("CALCULATED", "SENSITIVE") for r in recs.values()) == 2301
    for r in na:                                                                           # 금액을 만들지 않는다
        assert r["b"] is None and r["x"] is None
    assert all(r["t"] is None for r in recs.values() if any(w.startswith("TENURE_IMPLAUSIBLE") for w in r["w"]))


def test_company_page_links_only_for_real_corp_pages(recs):
    pages = set()
    for p in glob.glob(str(ROOT / "site/data/corp/*.json")):
        pages |= set(json.load(open(p, encoding="utf-8")).keys())
    linked = {c for c, r in recs.items() if r["p"]}
    assert linked == set(recs) & pages and len(linked) == 3682 and len(recs) - len(linked) == 230
    for c in linked:                                                                       # 연결된 코드는 실제 회사 샤드에 있다
        assert c in json.load(open(ROOT / f"site/data/corp/{int(c) % 128}.json", encoding="utf-8"))


def test_worked_example_samsung(recs):
    s = next(r for r in recs.values() if r["n"] == "삼성전자(주)")
    assert s["b"][3] == [11623, 12659] and s["x"][3] == [10931, 12842] and s["a"] == pytest.approx(15363.0, abs=1)


def test_public_site_has_no_experimental_assets(built):
    site = ROOT / "site"
    assert not (site / "exp.html").exists() and not (site / "data/exp").exists() and not list(site.glob("js/exp*")) and not (site / "css/exp.css").exists()
    for p in site.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css", ".json", ".txt"):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            assert "PAY WATCH LAB 실험적 추정" not in txt and "exp.html" not in txt and "LAB 실험" not in txt, p
    assert "exp.html" not in (site / "js/common.js").read_text(encoding="utf-8")
    assert list(site.glob("*.html")) and all("exp-embed" not in p.read_text(encoding="utf-8") for p in site.glob("*.html"))
    # PHASE 14: 별도 '연구용 검색' 화면·메뉴는 없고, 미리보기의 결과 화면(index·company)에만 연구용 로더가 붙는다
    assert not (PREV / "exp.html").exists() and "LAB 실험" not in (PREV / "js/common.js").read_text(encoding="utf-8")
    assert "exp-embed" in (PREV / "company.html").read_text(encoding="utf-8") and "exp-embed" in (PREV / "index.html").read_text(encoding="utf-8")


def test_preview_differs_from_site_only_by_experimental_additions(built):
    allowed = {"js/exp-section.js", "js/exp-embed.js", "js/exp-core.js", "css/exp.css", "PREVIEW_ONLY_NOT_FOR_PUBLIC.txt", "index.html", "company.html"}
    for p in PREV.rglob("*"):
        if not p.is_file(): continue
        rel = p.relative_to(PREV).as_posix()
        if rel.startswith("data/exp/") or rel in allowed: continue
        assert (ROOT / "site" / rel).read_bytes() == p.read_bytes(), rel


def test_web_exp_contains_only_code_and_no_banned_phrases():
    files = [p for p in (ROOT / "web_exp").rglob("*") if p.is_file()]
    assert files and all(p.suffix in (".html", ".js", ".css") for p in files)
    for p in files:
        t = p.read_text(encoding="utf-8")
        for bad in ("예상 적중률", "95% 신뢰구간", "실제 연봉 범위"):
            assert bad not in t, (p, bad)
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "preview/" in gi and "phase*_estimates.csv" in gi


def test_existing_lab_assets_untouched(built):
    assert (ROOT / "site/lab.html").exists() and (ROOT / "site/data/lab/lab.json").exists() and (PREV / "lab.html").exists()


def test_grade_display_rules_are_enforced_in_data(recs):
    """PHASE 12 등급 표시 규칙(A 범위 / B 범위+주의 / C 공시 평균만 / D 값 없음). 등급은 정확도가 아니라 공개 적합성이다."""
    G = pd.read_csv(WM / "phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    assert {r["c"]: r["g"] for r in recs.values()} == dict(zip(G.corp_code, G.등급))        # 등급 파일 그대로(새 임계값 없음)
    for r in recs.values():
        if r["g"] in ("C", "D"): assert r["b"] is None and r["x"] is None
        if r["g"] == "C": assert r["a"] is not None                                          # C: 공시 평균급여만
        if r["g"] == "D": assert r["a"] is None and r["t"] is None and r["e"] is None and r["d"] in ("NO_DATA", "DOUBT")
        if r["g"] in ("A", "B"): assert r["b"] is not None
    assert sum(r["d"] == "DOUBT" for r in recs.values() if r["g"] == "D") == 6
    raw = "".join(p.read_text(encoding="utf-8") for p in (PREV / "data/exp/f").glob("*.json"))
    c_or_d_with_range = [c for c, r in recs.items() if r["g"] in ("C", "D") and (r["b"] or r["x"])]
    assert not c_or_d_with_range and raw.count('"g":"D"') == 1598


def test_public_finder_index_has_names_ids_and_availability_flags_only(built):
    f = ROOT / "site/data/finder/entities.json"; rows = json.load(open(f, encoding="utf-8"))
    assert len(rows) == 3912 and all(len(r) == 6 and r[0].isdigit() and len(r[0]) == 8 and isinstance(r[4], int) and 0 <= r[4] <= 7 for r in rows)
    txt = f.read_text(encoding="utf-8")
    for bad in ("실험", "등급", "CALCULATED", "SENSITIVE", "INVALID", "INSUFFICIENT", "하한", "상한"): assert bad not in txt
    assert {r[0] for r in rows} == {r["c"] for r in json.load(open(ROOT / "preview/data/exp/index.json", encoding="utf-8")) for r in [{"c": r[0]}]}


def test_unified_flow_public_vs_preview_and_check_scripts(built):
    """PHASE 14: 공개 빌드 검사 스크립트와 링크 점검이 통과하고, 공개 파일에는 연구용 로더·데이터가 없다. 공시 값 의심 6곳은 공개 화면에서 숨겨진다."""
    import apply_public_policy  # noqa: F401  (pipeline 경로는 conftest 가 추가)
    py = [sys.executable, "-I", "-X", "utf8"]
    for script in ("apply_public_policy.py", "build_finder.py", "check_public.py", "check_links.py"):
        r = subprocess.run(py + [str(ROOT / "pipeline" / script)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, (script, r.stdout[-800:], r.stderr[-400:])
