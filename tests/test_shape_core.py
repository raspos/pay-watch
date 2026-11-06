"""shape_core(곡선 형태 민감도) 회귀 테스트: 기존 모형(range_core)을 그대로 재현하고, 신규 범위가 기존 범위를 포함하는지, 대안 곡선 선정 규칙을 확인."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
WM = ROOT / "reports/wage_model"
sys.path.insert(0, str(WM))
need = [WM / "phase2_company_comparison.csv", WM / "phase7_tenure_estimates.csv", WM / "d2_core.py", WM / "shape_core.py", ROOT / "data/raw/wage/wage_industry_basic_DT_118N_PAYN43.csv"]
pytestmark = pytest.mark.skipif(not all(p.exists() for p in need), reason="연구 산출물 없음")


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _mods():
    import d2_core, range_core, shape_core
    return d2_core, range_core, shape_core


def test_baseline_shape_reproduces_range_core_for_phase8_firms():
    d2, rc, sc = _mods()
    p2 = pd.read_csv(WM / "phase2_company_comparison.csv", encoding="utf-8-sig")
    S1 = pd.read_csv(WM / "phase7_tenure_estimates.csv", encoding="utf-8-sig").set_index("산업")
    for _, r in p2.iterrows():
        ind = r["산업중분류"]; A, sh, iavg = d2.industry(ind); lo, hi = float(S1.loc[ind, "m10 하한"]), float(S1.loc[ind, "m10 상한"])
        old = rc.range_for(A, sh, float(r["공시평균연봉_만원"]), float(r["평균근속_년"]), lo, hi)
        W, fam = sc.scenario_weights(sh, float(r["평균근속_년"]), lo, hi)
        assert len(W) == old["n"] and fam.count("F1") == old["nF1"]
        new = sc.curve_range(W, float(r["공시평균연봉_만원"]), A)
        assert np.allclose(new, old["rng"], rtol=1e-9), r["기업"]


def test_new_range_contains_old_and_alt_shapes_are_observed():
    d2, rc, sc = _mods()
    shapes = sc.load_shapes(); ten = sc.industry_tenure(); inv = {v: k for k, v in rc.division_map().items()}
    ind = "금융업"; A, sh, iavg = d2.industry(ind)
    alts, note, ok, ny, np_ = sc.alt_shapes(ind, shapes, ten, inv)
    assert ok and ny >= 1 and all(k in ("year", "peer") for _, k, _ in alts)
    S = np.vstack([A / iavg] + [s for _, _, s in alts])
    W, _ = sc.scenario_weights(sh, 15.6, 18.9, 21.6)
    old, new = sc.curve_range(W, 12431.0, A), sc.curve_range(W, 12431.0, S)
    assert (new[:, 0] <= old[:, 0] + 1e-9).all() and (new[:, 1] >= old[:, 1] - 1e-9).all()


def test_peer_rule_same_section_and_tenure_tolerance():
    d2, rc, sc = _mods()
    shapes = sc.load_shapes(); ten = sc.industry_tenure(); inv = {v: k for k, v in rc.division_map().items()}
    alts, *_ = sc.alt_shapes("자동차 및 트레일러 제조업", shapes, ten, inv)
    for label, kind, _ in alts:
        if kind == "peer":
            other = label[5:]
            assert sc.section_of(inv[other]) == "C" and abs(ten[other] - ten["자동차 및 트레일러 제조업"]) <= sc.TOL
    # 전기·가스·증기업은 대분류 D에 중분류가 하나뿐이라 유사 산업이 없다
    a2, *_ = sc.alt_shapes("전기, 가스, 증기 및 공기 조절 공급업", shapes, ten, inv)
    assert not any(k == "peer" for _, k, _ in a2)


def test_small_cell_industries_not_used_as_alternatives():
    d2, rc, sc = _mods()
    shapes = sc.load_shapes()
    assert shapes[("담배 제조업", 2025)]["ok"] is False            # 셀 인원 38명 등 소표본
    assert shapes[("금융업", 2025)]["ok"] is True
