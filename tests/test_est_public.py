"""공개 사이트의 근속 구간별 추정(실험적 추정) 데이터·화면 연결 검증. 최소 필드만 공개하고, 표시 대상이 아닌 기업과 보류값은 어디에도 없어야 한다."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
EST = SITE / "data/est/s"
pytestmark = pytest.mark.skipif(not EST.exists(), reason="공개 추정 데이터 없음(CI)")


def est_records():
    out = {}
    for p in EST.glob("*.json"):
        out.update(json.loads(p.read_text(encoding="utf-8")))
    return out


def test_public_estimate_data_is_minimal_and_covers_only_displayable_firms():
    recs = est_records()
    assert len(recs) == 1888                                                                 # 표시 대상: 범위가 있고 입력인 공시 평균급여가 검증을 통과한 기업만
    assert all(re.fullmatch(r"\d{8}", c) for c in recs)
    assert all(set(r) <= {"b", "x", "cau", "w", "y", "m"} and {"b", "cau", "y", "m"} <= set(r) and r["y"] == 2025 and r["m"] == "phase10-d2-shape-v1" for r in recs.values())      # 등급 글자·상태·공시 평균·근속·직원 수 없음
    assert sum(r["cau"] for r in recs.values()) == 1350 and sum(r["x"] is None for r in recs.values()) == 15
    for r in recs.values():
        assert len(r["b"]) == 5 and all(0 < lo <= hi for lo, hi in r["b"])
        if r["x"] is not None:
            assert all(x[0] <= b[0] and x[1] >= b[1] for x, b in zip(r["x"], r["b"]))      # 확대 범위는 기본 범위를 포함
    text = "".join(p.read_text(encoding="utf-8") for p in EST.glob("*.json"))
    for bad in ('"g"', '"s"', '"a"', '"t"', '"e"', "CALCULATED", "SENSITIVE", "INVALID", "등급"):
        assert bad not in text


def test_firms_without_displayable_range_have_no_estimate_record():
    recs = est_records()
    import pandas as pd
    g = ROOT / "reports/wage_model/phase12_firm_grades.csv"
    if not g.exists():
        pytest.skip("등급 파일 없음(CI)")
    df = pd.read_csv(g, encoding="utf-8-sig", dtype={"corp_code": str})
    shown = set(df[df.등급.isin(["A", "B"])].corp_code)
    assert set(recs) <= shown and len(shown - set(recs)) == 250                              # 표시 대상 중 입력 공시 급여가 보류된 250곳은 제외
    assert "00149044" not in recs                                                            # (주)조선일보사: 2025 직원현황 없음 → 모형 입력 없음 → 숫자를 만들지 않는다
    assert not (set(df[df.등급.isin(["C", "D"])].corp_code) & set(recs))


def test_estimates_are_never_built_on_held_dart_pay():
    """추정은 DART 공시 평균급여를 입력으로 쓴다. 급여 정합성 때문에 보류된 기업(level != ok·hold)은 추정을 공개하지 않는다."""
    corp = {}
    for p in (SITE / "data/corp").glob("*.json"):
        corp.update(json.loads(p.read_text(encoding="utf-8")))
    held = {c for c, r in corp.items() if r.get("hold") or (r.get("dart") and r["dart"].get("level") != "ok")}
    assert len(held) >= 300 and not (held & set(est_records()))
    assert all("a" not in r for r in est_records().values())
    meta = json.loads((SITE / "data/est/meta.json").read_text(encoding="utf-8"))
    assert meta["firms"] == 1888 and meta["ref_year"] == 2025 and meta["bins"] == ["1년 미만", "1~3년", "3~5년", "5~10년", "10년 이상"] and meta["model_version"]
    src = (SITE / "js/est-embed.js").read_text(encoding="utf-8")
    assert "dartAvg" in src and "__pwResult" in src


def test_company_page_loads_estimate_area_and_public_site_has_no_internal_research_files():
    html = (SITE / "company.html").read_text(encoding="utf-8")
    assert "est-embed.js" in html and "est.css" in html
    assert not (SITE / "data/exp").exists() and not list(SITE.glob("js/exp*")) and not (SITE / "exp.html").exists()
    for must in ("근속 구간 집단의 평균급여 · 실험적 추정", "개인 연봉이나 통계적 신뢰구간이 아니며", "정확도는 검증되지 않았습니다"):
        assert must in (SITE / "js/est-section.js").read_text(encoding="utf-8")                # 숫자 가까이의 필수 안내
