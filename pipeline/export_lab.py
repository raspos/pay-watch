"""PAY WATCH LAB 데이터 내보내기: 2025 고용형태별노동실태조사(성별 전체)의 산업×근속, 직종×경력 구간 평균을 site/data/lab/lab.json 으로.
- 새 데이터 수집 없음: data/raw/wage/ 의 CSV 두 개만 읽는다(PHASE 0.5).
- 값은 월임금총액(천원)을 그대로 정수로 저장한다. 연환산(×12)·만원 변환은 화면 계산 단계에서 하고, 반올림은 표시할 때만 한다.
- CSV 에 없는 분류·구간은 만들지 않는다. 비공개/누락 셀은 null(0 아님).
- build_site.py 는 site/data 를 건드리지 않으므로 이 파일은 빌드로 삭제되지 않는다."""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/wage"
OUT = ROOT / "site/data/lab/lab.json"
YEAR = 2025
IND_BINS = ["1년미만", "1~3년미만", "3~5년미만", "5~10년미만", "10년이상"]      # 표기 통일(원자료 산업 표는 '1-3년미만')
OCC_BINS = list(IND_BINS)
SRC_IND = RAW / "wage_industry_tenure_DT_118N_PAYN49.csv"
SRC_OCC = RAW / "wage_occupation_career_DT_118N_PAYM47.csv"


def _norm_bin(b: str) -> str:
    return b.replace("-", "~")


def _load(path: Path, cols: list[str]) -> pd.DataFrame:
    d = pd.read_csv(path, encoding="utf-8-sig")
    keep = {d.columns[0]: "year", d.columns[1]: "cls", d.columns[2]: "sex", d.columns[3]: "bin"}
    for c in d.columns:
        if c.startswith("월임금총액"):
            keep[c] = "m"
        elif c.startswith("근로자수"):
            keep[c] = "n"
    d = d.rename(columns=keep)[["year", "cls", "sex", "bin", "m", "n"]]
    d = d[(d.year == YEAR) & (d.sex == "전체")].copy()
    d["bin"] = d["bin"].map(_norm_bin)
    return d


def _num(v):
    x = pd.to_numeric(v, errors="coerce")
    return None if pd.isna(x) else int(x) if float(x).is_integer() else float(x)


def _classify_industry(name: str):
    if name == "전체":
        return "전체", None, name
    m = re.match(r"^([A-Z])\.\s*(.*?)\s*\(([^)]*)\)\s*$", name)
    if m:
        return "대분류", f"{m.group(1)}({m.group(3)})", m.group(2)
    return "중분류", None, name


def _classify_occupation(name: str):
    if name == "전직종":
        return "전체", None, name
    m = re.match(r"^(.*?)\s*\((\d+)\)\s*$", name)
    if m:
        code = m.group(2)
        return {1: "대분류", 2: "중분류", 3: "소분류"}.get(len(code), "기타"), code, m.group(1).strip()
    return "기타", None, name


def build(d: pd.DataFrame, bins: list[str], classify, all_label: str) -> list[dict]:
    items = []
    order = list(dict.fromkeys(d["cls"]))                       # CSV 순서 유지
    for cls in order:
        g = d[d.cls == cls].set_index("bin")
        level, code, name = classify(cls)
        m = [_num(g.loc[b, "m"]) if b in g.index else None for b in bins]
        n = [_num(g.loc[b, "n"]) if b in g.index else None for b in bins]
        allrow = [k for k in g.index if k.startswith("전")]
        items.append({"id": len(items), "name": name, "raw": cls, "level": level, "code": code, "m": m, "n": n,
                      "mAll": _num(g.loc[allrow[0], "m"]) if allrow else None, "nAll": _num(g.loc[allrow[0], "n"]) if allrow else None})
    return items


def main():
    ind, occ = _load(SRC_IND, []), _load(SRC_OCC, [])
    data = {
        "meta": {"year": YEAR, "sex": "전체", "unit": "월임금총액 천원(연환산=×12)", "bins": {"industry": IND_BINS, "occupation": OCC_BINS},
                 "source": "고용노동부 고용형태별노동실태조사(고용노동통계포털) — DT_118N_PAYN49(산업,근속년수,성별), DT_118N_PAYM47(직종,경력년수,성별)",
                 "population": "상용 5인 이상 상용근로자 계열(구 임금구조기본통계조사) 추정", "note": "구간 평균. 개별 연차·중위값·분위수 없음. null=비공개·누락"},
        "industry": build(ind, IND_BINS, _classify_industry, "전체"),
        "occupation": build(occ, OCC_BINS, _classify_occupation, "전직종"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    sz = OUT.stat().st_size
    nulls = sum(v is None for k in ("industry", "occupation") for it in data[k] for v in it["m"])
    print(f"lab.json {sz:,}B 산업 {len(data['industry'])} 직종 {len(data['occupation'])} 분류, 월임금 null 셀 {nulls}")
    return data


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
