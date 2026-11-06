"""PHASE 11 연구용(실험적) 기업별 추정 범위 JSON 내보내기. **공개용 site/ 에는 쓰지 않는다**: 출력 위치는 build_preview.py 가 만드는 preview/data/exp/ 뿐이다.
입력은 저장된 연구 결과만 사용한다(새 계산·새 수집 없음):
  - reports/wage_model/phase12_ranges_rawprecision.csv : PHASE 10 모형을 DART 원자료 정밀도(반올림 전 평균급여·평균근속)로 다시 계산한 기본 범위([기존])·확대 범위([신규], 형태 실험 '실행'인 기업만).
    PHASE 10 CSV(phase10_shape_estimates.csv)는 반올림된 입력을 썼고 신풍제약 1곳에서 시나리오 수가 달라져 0.5% 넘게 다르므로(PHASE 12 감사) 이 파일을 웹 데이터의 근거로 쓴다. 나머지는 상대 차이 0.05% 안팎이다.
  - reports/wage_model/phase9_group_a_quality.csv   : A그룹 2,320곳의 상태·사유·공시 평균급여·평균근속·산업
DART 법인코드는 8자리 문자열로 다룬다. PHASE 10 CSV 는 앞자리 0 이 사라져 저장돼 있어 zfill(8) 후 DART 캐시 원본 코드와 대조(검증 실패 시 중단)한다.
  - reports/wage_model/phase12_firm_grades.csv      : PHASE 12 공개 적합성 등급 A~D(캐시 3,912곳). **등급은 정확도 등급이 아니다.** 표시 규칙(PHASE 13, 새 임계값 없음):
      A 기본·확대 범위 표시 / B 범위 + 민감도 주의 / C 범위 없음, 공시 평균급여만 / D 어떤 급여 값도 없음(자료 부족 또는 공시 값 의심 → 이유만).
      C·D 의 범위(b·x)는 JS 에서 가리는 것이 아니라 **JSON 에 아예 쓰지 않는다**(null). D 는 공시 평균급여(a)도 쓰지 않는다(공시 값 의심 6곳의 값이 곧 의심 대상이다).
금액 단위는 만원 정수(연환산 평균급여, 연구 CSV 와 동일). 결과가 없는 기업(INVALID·INSUFFICIENT, 형태 실험 보류의 확대 범위)에는 어떤 금액도 만들지 않는다(null)."""
import glob
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WM = ROOT / "reports/wage_model"
BINS = ["1년미만", "1~3년미만", "3~5년미만", "5~10년미만", "10년이상"]
SHARDS = 64
LABEL = "PAY WATCH LAB 실험적 추정"


def short_name(n: str) -> str:
    return re.sub(r"\(주\)|주식회사|㈜", "", str(n)).strip()


def cache_codes() -> set:
    return {Path(p).name.split("_")[0] for p in glob.glob(str(ROOT / "data/raw/dart/cache/empSttus/*_2025_11011.json"))}


def corp_page_codes() -> set:
    """기존 회사 상세(company.html?corp=코드)가 실제로 있는 DART 코드 = site/data/corp 샤드의 키."""
    out = set()
    for p in glob.glob(str(ROOT / "site/data/corp/*.json")):
        out |= set(json.load(open(p, encoding="utf-8")).keys())
    return out


def load_grades() -> pd.DataFrame:
    G = pd.read_csv(WM / "phase12_firm_grades.csv", encoding="utf-8-sig", dtype={"corp_code": str})
    assert G.corp_code.str.fullmatch(r"\d{8}").all() and not G.corp_code.duplicated().any(), "등급 파일 코드 형식·중복"
    assert set(G.등급) <= {"A", "B", "C", "D"}
    return G


def build_records() -> list[dict]:
    Q = pd.read_csv(WM / "phase9_group_a_quality.csv", encoding="utf-8-sig", dtype={"corp_code": str}); Q = Q[Q.A그룹 == True].copy()      # noqa: E712
    E = pd.read_csv(WM / "phase12_ranges_rawprecision.csv", encoding="utf-8-sig", dtype={"corp_code": str}); E["corp_code"] = E["corp_code"].str.zfill(8)
    codes = cache_codes(); pages = corp_page_codes()
    assert Q.corp_code.str.fullmatch(r"\d{8}").all() and not Q.corp_code.duplicated().any(), "A그룹 코드 형식·중복"
    assert set(Q.corp_code) <= codes, "A그룹 코드가 DART 캐시 원본에 없음"
    assert set(E.corp_code) <= set(Q.corp_code), "PHASE 10 코드(zfill 후)가 A그룹에 없음"
    G = load_grades(); assert set(Q.corp_code) <= set(G.corp_code) and set(G.corp_code) <= codes, "등급 파일이 A그룹을 포함하지 않거나 캐시에 없는 코드가 있음"
    grade_of = dict(zip(G.corp_code, G.등급)); gname = dict(zip(G.corp_code, G.기업명))
    recs = []
    by = {c: g for c, g in E.groupby("corp_code")}
    for _, r in Q.iterrows():
        status = r["상태"]; calc = status in ("CALCULATED", "SENSITIVE")
        rec = {"c": r.corp_code, "n": r["기업명"], "k": short_name(r["기업명"]), "s": status, "i": None if pd.isna(r["노동부산업"]) else r["노동부산업"], "m": r["시장구분"],
               "e": None if pd.isna(r["직원수"]) else int(r["직원수"]), "a": None if pd.isna(r["공시평균_만원"]) else float(r["공시평균_만원"]), "t": None if pd.isna(r["평균근속_년"]) else float(r["평균근속_년"]),
               "w": [x for x in str(r["사유"]).split(";") if x and x != "nan"], "b": None, "x": None, "h": False, "p": r.corp_code in pages}
        reasons = rec["w"]
        if any(x.startswith("TENURE_IMPLAUSIBLE") for x in reasons): rec["t"] = None             # 비현실적 평균근속은 표시하지 않는다(자료 오류 의심)
        if calc:
            g = by[r.corp_code].set_index("구간")
            assert list(g.index) == BINS or set(g.index) == set(BINS)
            rec["b"] = [[int(g.loc[b, "[기존] 하한_만원"]), int(g.loc[b, "[기존] 상한_만원"])] for b in BINS]
            ran = g["형태실험"].iloc[0] == "실행"
            rec["h"] = not ran
            if ran:
                rec["x"] = [[int(g.loc[b, "[신규] 하한_만원"]), int(g.loc[b, "[신규] 상한_만원"])] for b in BINS]
        else:
            assert r.corp_code not in by, "추정 불가 기업에 범위가 있음"
        g = grade_of[r.corp_code]; rec["g"] = g
        if g in ("C", "D"):
            rec["b"] = None; rec["x"] = None; rec["h"] = False                                # C·D 는 추정 범위를 데이터에 싣지 않는다
        if g == "D":
            rec["a"] = None; rec["t"] = None; rec["e"] = None; rec["d"] = "DOUBT"           # 공시 값 의심: 값 자체를 싣지 않는다
        recs.append(rec)
    for c in sorted(set(G.corp_code) - set(Q.corp_code)):                                   # A그룹이 아닌 기업(자료 부족): 이름·식별자·이유만
        assert grade_of[c] == "D", "A그룹이 아닌데 D 가 아닌 등급"
        recs.append({"c": c, "n": gname[c], "k": short_name(gname[c]), "g": "D", "s": None, "i": None, "m": None, "e": None, "a": None, "t": None, "w": [], "b": None, "x": None, "h": False, "p": c in pages, "d": "NO_DATA"})
    check_records(recs)
    return recs


def check_records(recs: list[dict]) -> None:
    """공개 적합성 표시 규칙을 데이터 단계에서 강제한다(어기면 중단)."""
    codes = [r["c"] for r in recs]; assert len(codes) == len(set(codes)) and all(re.fullmatch(r"\d{8}", c) for c in codes)
    for r in recs:
        assert r["g"] in ("A", "B", "C", "D"), r["c"]
        if r["g"] in ("C", "D"): assert r["b"] is None and r["x"] is None, f"{r['c']} 등급 {r['g']} 에 범위가 있음"
        if r["g"] == "D": assert r["a"] is None and r["t"] is None and r["e"] is None, f"{r['c']} D 등급에 급여 값이 있음"
        if r["g"] in ("A", "B"): assert r["b"] is not None, f"{r['c']} 등급 {r['g']} 에 기본 범위가 없음"


def export(outdir: Path) -> dict:
    outdir = Path(outdir); (outdir / "f").mkdir(parents=True, exist_ok=True)
    recs = build_records()
    shards: dict[int, dict] = {i: {} for i in range(SHARDS)}
    for r in recs:
        shards[int(r["c"]) % SHARDS][r["c"]] = r
    for i, d in shards.items():
        (outdir / "f" / f"{i}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    idx = [[r["c"], r["n"], r["k"], r["g"], 1 if r["p"] else 0, r["e"] or 0, r["i"] or "", r.get("d", "")] for r in recs]
    (outdir / "index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    meta = {"label": LABEL, "n": len(recs), "calculated": sum(r["s"] in ("CALCULATED", "SENSITIVE") for r in recs), "sensitive": sum(r["s"] == "SENSITIVE" for r in recs),
            "shape_run": sum(r["x"] is not None for r in recs), "shape_held": sum(r["h"] for r in recs), "not_estimated": sum(r["b"] is None for r in recs), "grades": {g: sum(r["g"] == g for r in recs) for g in "ABCD"}, "with_company_page": sum(r["p"] for r in recs),
            "shards": SHARDS, "bins": BINS, "unit": "만원(연환산 평균급여)", "base": "기본 범위(원자료 정밀도 재계산)", "expanded": "확대 범위(원자료 정밀도 재계산)"}
    (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (outdir / "README_NOT_FOR_PUBLIC.txt").write_text("PAY WATCH LAB 실험적 추정 데이터. PHASE 12 통합 검증 전까지 외부 공개 금지(공개 저장소·site/ 에 포함하지 않는다).\n", encoding="utf-8")
    return meta


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview/data/exp"
    if ROOT / "site" in out.resolve().parents or out.resolve() == ROOT / "site":
        sys.exit("site/ 아래에는 실험 데이터를 쓰지 않는다")
    print(export(out))
