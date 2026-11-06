"""PHASE 12: 감사 결과 CSV, 공개 적합성 등급 규칙, 미리보기 서버 바인딩, 공개 분리를 검증한다."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
WM = ROOT / "reports/wage_model"
sys.path.insert(0, str(WM)); sys.path.insert(0, str(ROOT / "pipeline"))
need = [WM / "phase12_audit_checks.csv", WM / "phase12_firm_grades.csv", WM / "phase12_ranges_rawprecision.csv", WM / "phase9_group_a_quality.csv", ROOT / "data/raw/dart/cache"]   # 원자료·비공개 연구 CSV 가 없는 환경(CI)에서는 건너뜀
pytestmark = pytest.mark.skipif(not all(p.exists() for p in need), reason="감사 산출물 없음")


def test_audit_checks_all_pass_except_documented_rounding_case():
    ch = pd.read_csv(WM / "phase12_audit_checks.csv", encoding="utf-8-sig")
    assert len(ch) >= 25
    bad = ch[ch["결과"] != "통과"]
    known = {"기본 범위: 원자료 정밀도 재계산과 PHASE 10 저장값(반올림 입력)의 상대 차이 1% 이하", "확대 범위: 원자료 정밀도 재계산과 PHASE 10 저장값(반올림 입력)의 상대 차이 1% 이하",
             "원자료 정밀도 재계산과 PHASE 10 저장값이 0.5% 넘게 다른 기업", "반올림된 평균근속 입력과 원자료 정밀도에서 양립 시나리오 수(수학적 제약 판정)가 달라지는 기업"}
    assert set(bad["검증 항목"]) == known, bad[["검증 항목", "불일치", "비고"]].to_string()
    assert set(bad["불일치"]) <= {1, 5} and bad[bad["검증 항목"].str.contains("0.5% 넘게|양립 시나리오 수")]["비고"].str.contains("신풍제약").all()


def test_rawprecision_ranges_match_phase9_and_have_sane_structure():
    r = pd.read_csv(WM / "phase12_ranges_rawprecision.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    p9 = pd.read_csv(WM / "phase9_group_a_estimates.csv", encoding="utf-8-sig", dtype={"corp_code": str}); p9["corp_code"] = p9.corp_code.str.zfill(8)
    m = r.merge(p9[["corp_code", "구간", "[모형 가정 범위] 하한_만원", "[모형 가정 범위] 상한_만원"]], on=["corp_code", "구간"])
    assert len(m) == 11505 == len(r) and r.corp_code.str.fullmatch(r"\d{8}").all()
    assert ((m["[기존] 하한_만원"] - m["[모형 가정 범위] 하한_만원"]).abs() <= 1).all() and ((m["[기존] 상한_만원"] - m["[모형 가정 범위] 상한_만원"]).abs() <= 1).all()
    assert (r["[기존] 하한_만원"] <= r["[기존] 상한_만원"]).all() and (r["[기존] 하한_만원"] > 0).all()
    x = r[r["[신규] 하한_만원"].notna()]
    assert (x["[신규] 하한_만원"] <= x["[기존] 하한_만원"] + 1).all() and (x["[신규] 상한_만원"] >= x["[기존] 상한_만원"] - 1).all()
    assert r[r.형태실험 == "보류"]["[신규] 하한_만원"].isna().all() and r[r.형태실험 == "보류"].corp_code.nunique() == 16


def test_grade_rules_are_deterministic_and_separate_from_status():
    from publication_grade import grade
    base = dict(in_a=True, integrity_ok=True, status="CALCULATED", reasons=[], shape_run=True, exp_width_max=0.2, consistency=0.01)
    assert grade(base)[0] == "A"
    assert grade({**base, "exp_width_max": 0.31})[0] == "B" and grade({**base, "shape_run": False})[0] == "B"
    assert grade({**base, "exp_width_max": 0.31}, w=0.4)[0] == "A"                         # 폭 기준은 판단 사항(민감도 확인용)
    assert grade({**base, "status": "SENSITIVE", "reasons": ["THRESHOLD_BAND(1.25~2.00)"]})[0] == "B"
    assert grade({**base, "status": "SENSITIVE", "reasons": ["EXTRAPOLATION_BEYOND_ALL_THRESHOLDS(>2.00)"]})[0] == "C"
    assert grade({**base, "status": "SENSITIVE", "reasons": ["MAPPING_RISK_NAME(HOLDING)"]})[0] == "C"
    assert grade({**base, "status": "SENSITIVE", "reasons": ["PAY_CONSISTENCY(>5%)"], "consistency": 0.3})[0] == "C"
    assert grade({**base, "status": "SENSITIVE", "reasons": ["PAY_CONSISTENCY(>5%)"], "consistency": 0.1})[0] == "B"
    assert grade({**base, "status": "INSUFFICIENT", "reasons": ["NO_INDUSTRY_CODE"]})[0] == "C"
    assert grade({**base, "status": "INVALID", "reasons": ["MATH_INFEASIBLE:M10_RANGE_EMPTY"]})[0] == "C"
    assert grade({**base, "status": "INVALID", "reasons": ["TENURE_IMPLAUSIBLE"]})[0] == "D" and grade({**base, "status": "INVALID", "reasons": ["MAPPING_SUSPECT_LEVEL(공시/산업 평균 8.44)"]})[0] == "D"
    assert grade({**base, "in_a": False})[0] == "D" and grade({**base, "integrity_ok": False})[0] == "D"


def test_firm_grades_cover_all_cached_firms_and_keep_status():
    g = pd.read_csv(WM / "phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    assert len(g) == 3912 and g.corp_code.is_unique and set(g.등급) == {"A", "B", "C", "D"}
    q = pd.read_csv(WM / "phase9_group_a_quality.csv", encoding="utf-8-sig", dtype={"corp_code": str}).set_index("corp_code")
    assert (g.set_index("corp_code").상태 == q.loc[g.corp_code, "상태"].values).all()       # 기존 상태는 그대로 유지
    assert set(g[g.상태.isin(["INVALID", "INSUFFICIENT"])].등급) <= {"C", "D"}
    assert set(g[g.상태 == "CALCULATED"].등급) <= {"A", "B"} and set(g[g.상태 == "SENSITIVE"].등급) <= {"B", "C"}


def test_preview_server_binds_loopback_only():
    import serve_preview
    assert serve_preview.HOST == "127.0.0.1"
    prev = ROOT / "preview"
    if prev.exists():
        srv = serve_preview.make_server(0, prev)
        try:
            assert srv.server_address[0] == "127.0.0.1"
        finally:
            srv.server_close()


def test_public_site_has_no_experimental_data_names_or_markers():
    site = ROOT / "site"
    names = [p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()]
    assert not [n for n in names if "exp" in n.lower().replace("explain", "").split("/")[-1] and (n.startswith("data/exp") or n.startswith("js/exp") or n == "exp.html")]
    for p in site.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css", ".json", ".txt"):
            t = p.read_text(encoding="utf-8", errors="ignore")
            assert "실험적 추정" not in t and "data/exp" not in t and "LAB 실험" not in t, p
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "preview/" in gi
