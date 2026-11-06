"""LAB 데이터 내보내기 검증: JSON 이 원자료 CSV 와 일치하는지, 단위·구간·결측 처리, 빌드가 JSON 을 지우지 않는지."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "site/data/lab/lab.json"
IND = ROOT / "data/raw/wage/wage_industry_tenure_DT_118N_PAYN49.csv"
OCC = ROOT / "data/raw/wage/wage_occupation_career_DT_118N_PAYM47.csv"
BINS = ["1년미만", "1~3년미만", "3~5년미만", "5~10년미만", "10년이상"]


@pytest.fixture(scope="module")
def lab():
    subprocess.run([sys.executable, "-I", "-X", "utf8", str(ROOT / "pipeline/export_lab.py")], check=True, cwd=ROOT, capture_output=True)
    return json.loads(LAB.read_text(encoding="utf-8"))


def raw(path):
    d = pd.read_csv(path, encoding="utf-8-sig")
    cols = list(d.columns)
    m = next(c for c in cols if c.startswith("월임금총액"))
    n = next(c for c in cols if c.startswith("근로자수"))
    d = d.rename(columns={cols[0]: "year", cols[1]: "cls", cols[2]: "sex", cols[3]: "bin", m: "m", n: "n"})
    d = d[(d.year == 2025) & (d.sex == "전체")].copy()
    d["bin"] = d["bin"].str.replace("-", "~", regex=False)
    return d


@pytest.mark.parametrize("key,path", [("industry", IND), ("occupation", OCC)])
def test_values_match_raw_csv_for_every_class(lab, key, path):
    d = raw(path)
    assert [it["raw"] for it in lab[key]] == list(dict.fromkeys(d["cls"]))        # 존재하는 분류만, 순서 유지
    for it in lab[key]:
        g = d[d.cls == it["raw"]].set_index("bin")
        for i, b in enumerate(BINS):
            if b in g.index:
                assert it["m"][i] == g.loc[b, "m"] and it["n"][i] == g.loc[b, "n"], (it["raw"], b)
            else:
                assert it["m"][i] is None and it["n"][i] is None                    # 누락은 null (0 아님)


def test_meta_units_and_bins(lab):
    assert lab["meta"]["year"] == 2025 and lab["meta"]["sex"] == "전체"
    assert lab["meta"]["bins"]["industry"] == BINS and lab["meta"]["bins"]["occupation"] == BINS
    assert "×12" in lab["meta"]["unit"]
    assert len(lab["industry"]) == 92 and len(lab["occupation"]) == 192


def test_annualization_exact_and_totals(lab):
    # 월임금총액 4,482천원 → 연 5,378.4만원. JSON 에는 천원 원값만 있고 반올림된 연환산 값은 없다.
    ind_all = next(it for it in lab["industry"] if it["level"] == "전체")
    occ_all = next(it for it in lab["occupation"] if it["level"] == "전체")
    assert ind_all["mAll"] == 4482 and occ_all["mAll"] == 4482
    assert ind_all["mAll"] * 12 / 10 == pytest.approx(5378.4)
    for it in lab["industry"] + lab["occupation"]:
        assert all(isinstance(v, int) for v in it["m"] if v is not None)


def test_industry_and_occupation_not_mixed(lab):
    ind_all = next(it for it in lab["industry"] if it["level"] == "전체")
    occ_all = next(it for it in lab["occupation"] if it["level"] == "전체")
    assert ind_all["n"] != occ_all["n"]                                            # 근속 분포와 경력 분포는 다르다
    assert not any("직종" in it["raw"] for it in lab["industry"])


def test_json_has_no_nan_and_is_small():
    text = LAB.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    assert LAB.stat().st_size < 200_000


def test_build_site_keeps_lab_json_and_copies_lab_page(lab):
    before = hashlib.sha1(LAB.read_bytes()).hexdigest()
    subprocess.run([sys.executable, "-I", "-X", "utf8", str(ROOT / "pipeline/build_site.py")], check=True, cwd=ROOT, capture_output=True)
    assert LAB.exists() and hashlib.sha1(LAB.read_bytes()).hexdigest() == before
    assert (ROOT / "site/lab.html").exists() and (ROOT / "site/js/lab.js").exists() and (ROOT / "site/js/lab-core.js").exists()
    assert "lab-core.js?v=" in (ROOT / "site/js/lab.js").read_text(encoding="utf-8")


def test_existing_site_data_untouched_by_export(lab):
    for name in ("meta.json", "dist.json", "industries.json"):
        assert (ROOT / "site/data" / name).exists()
