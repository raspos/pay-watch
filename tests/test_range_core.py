"""range_core(배치 범위 모형)가 PHASE 8 결과(phase8_scenarios.csv, 10개 기업)를 재현하는지 회귀 테스트."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
WM = ROOT / "reports/wage_model"
sys.path.insert(0, str(WM))
need = [WM / "phase2_company_comparison.csv", WM / "phase7_tenure_estimates.csv", WM / "phase8_scenarios.csv", WM / "d2_core.py"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in need), reason="연구 산출물 없음")


def _load():
    import d2_core, range_core
    return d2_core, range_core


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)                                         # d2_core·range_core 가 상대 경로로 CSV 를 읽는다(다른 테스트에 영향 없도록 복구)


def test_composition_matches_d2_core():
    d2, rc = _load()
    A, sh, iavg = d2.industry("금융업")
    for T, m10 in ((15.6, 20.0), (13.7, 17.5), (10.0, 25.0)):
        a, b = d2.composition(sh, T, m10), rc.composition(sh, T, m10)
        assert np.allclose(a, b, atol=1e-9)


def test_batch_range_reproduces_phase8_for_all_10_firms():
    d2, rc = _load()
    p2 = pd.read_csv(WM / "phase2_company_comparison.csv", encoding="utf-8-sig")
    S1 = pd.read_csv(WM / "phase7_tenure_estimates.csv", encoding="utf-8-sig").set_index("산업")
    sc = pd.read_csv(WM / "phase8_scenarios.csv", encoding="utf-8-sig")
    assert len(p2) == 10
    for _, r in p2.iterrows():
        A, sh, iavg = d2.industry(r["산업중분류"])
        res = rc.range_for(A, sh, float(r["공시평균연봉_만원"]), float(r["평균근속_년"]), float(S1.loc[r["산업중분류"], "m10 하한"]), float(S1.loc[r["산업중분류"], "m10 상한"]))
        ok = sc[(sc.기업 == r["기업"]) & sc.양립]
        assert res["n"] == len(ok), r["기업"]
        assert res["nF1"] == int((ok.가정 == "F1").sum()) and res["nF2"] == int((ok.가정 == "F2").sum())
        assert abs(res["rng"][0, 0] - ok.곡선_1년미만.min()) < 0.5 and abs(res["rng"][0, 1] - ok.곡선_1년미만.max()) < 0.5, r["기업"]


def test_division_map_complete_and_ordered():
    _, rc = _load()
    m = rc.division_map()
    assert len(m) == 73 and m[26].startswith("전자 부품") and m[30].startswith("자동차") and m[64] == "금융업" and m[63] == "정보서비스업" and m[58] == "출판업"
    assert 84 not in m and 84 in rc.KSIC_DIVISIONS                     # 공공행정은 노동부 표에 없음


def test_no_valid_range_when_tenure_not_below_official_m10():
    d2, rc = _load()
    A, sh, iavg = d2.industry("금융업")
    res = rc.range_for(A, sh, 10000.0, 30.0, 18.9, 21.6)               # 평균근속이 산업 m10 범위보다 크면 양립 시나리오 없음
    assert res["rng"] is None and res["n"] == 0 and res["reason"]
