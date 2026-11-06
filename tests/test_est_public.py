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
    assert len(recs) == 2138                                                                 # 표시 대상(범위가 있는 기업)만
    assert all(re.fullmatch(r"\d{8}", c) for c in recs)
    assert all(set(r) <= {"b", "x", "cau", "w"} and {"b", "cau"} <= set(r) for r in recs.values())      # 등급 글자·상태·공시 평균·근속·직원 수 없음
    assert sum(r["cau"] for r in recs.values()) == 1599 and sum(r["x"] is None for r in recs.values()) == 16
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
    assert set(recs) == shown                                                                # C·D 등급 기업은 레코드 자체가 없다 → 화면에서 영역이 그려지지 않는다
    assert not (set(df[df.등급.isin(["C", "D"])].corp_code) & set(recs))


def test_held_dart_firms_get_estimates_without_leaking_their_pay_value():
    """공시 급여가 보류된 기업도 추정 범위가 있을 수 있다. 이때 공개 추정 데이터에는 기업 평균(a)이 없고, 그래프 기준선은 화면이 넘긴 값(보류면 null)만 쓴다."""
    corp = {}
    for p in (SITE / "data/corp").glob("*.json"):
        corp.update(json.loads(p.read_text(encoding="utf-8")))
    held = {c for c, r in corp.items() if r.get("dart") and r["dart"].get("level") != "ok"}
    both = held & set(est_records())
    assert both                                                                              # 보류 + 추정 기업이 실제로 있다
    assert all("a" not in est_records()[c] for c in both)
    src = (SITE / "js/est-embed.js").read_text(encoding="utf-8")
    assert "dartAvg" in src and "__pwResult" in src


def test_company_page_loads_estimate_area_and_public_site_has_no_internal_research_files():
    html = (SITE / "company.html").read_text(encoding="utf-8")
    assert "est-embed.js" in html and "est.css" in html
    assert not (SITE / "data/exp").exists() and not list(SITE.glob("js/exp*")) and not (SITE / "exp.html").exists()
    for must in ("근속 구간 집단의 평균급여 · 실험적 추정", "개인 연봉이나 통계적 신뢰구간이 아니며", "정확도는 검증되지 않았습니다"):
        assert must in (SITE / "js/est-section.js").read_text(encoding="utf-8")                # 숫자 가까이의 필수 안내
