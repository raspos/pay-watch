"""Stage 1 실행: 적재 → 정제 → 추정 → 품질 리포트 → 10개 기업 표.
사용: python pipeline/run_stage1.py data/raw/nps/nps_2026-09.csv"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch import METHODOLOGY_VERSION  # noqa: E402
from paywatch.estimate_salary import estimate  # noqa: E402
from paywatch.load_nps import clean, read_nps_csv  # noqa: E402
from paywatch.tables import CONFIG_DIR, load_caps, load_rates  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def won(x):
    return "—" if pd.isna(x) else f"{x:,.0f}"


def main(csv_path: str):
    raw, meta = read_nps_csv(Path(csv_path))
    if len(meta["ym_values"]) != 1:
        raise SystemExit(f"파일 안의 자료생성년월이 1개가 아닙니다: {meta['ym_values']}")
    ym = meta["ym_values"][0]

    ok, quarantine = clean(raw)
    est = estimate(ok, load_rates(), load_caps())

    (ROOT / "data/interim").mkdir(exist_ok=True, parents=True)
    est.to_parquet(ROOT / f"data/interim/nps_{ym}.parquet", index=False)
    quarantine.to_csv(ROOT / f"data/interim/quarantine_{ym}.csv", index=False, encoding="utf-8-sig")

    # 원본 해시 기록(커밋 대상)
    man = ROOT / "data/raw/nps/raw_manifest.csv"
    new = not man.exists()
    if not new and meta["sha256"] in man.read_text(encoding="utf-8"):
        pass  # 같은 해시가 이미 기록됨(재실행 시 중복 행 방지)
    else:
      with open(man, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file_name", "ym", "sha256", "size_bytes", "rows", "encoding", "loaded_at"])
        w.writerow([meta["file_name"], ym, meta["sha256"], meta["size_bytes"], meta["rows"], meta["encoding"], meta["loaded_at"]])

    quality_report(est, quarantine, meta, ym)
    benchmark_report(est, ym)
    (ROOT / f"reports/quality/run_manifest_{ym}.json").write_text(
        json.dumps({**meta, "methodology_version": METHODOLOGY_VERSION,
                    "rates_sha": None, "ym": ym}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", ym, len(est), len(quarantine))


def quality_report(est, q, meta, ym):
    e = est
    pub = e[e["pay_public"]]
    L = [f"# 데이터 품질 리포트 — {ym} (Stage 1)", "",
         f"- 원본: `{meta['file_name']}` / {meta['size_bytes']:,} bytes / SHA-256 `{meta['sha256']}`",
         f"- 인코딩(실측): {meta['encoding']} / 원본 행 수: {meta['rows']:,} / 자료생성년월: {meta['ym_values']}",
         f"- 정제 후 행 수: {len(e):,} / 격리(제외) 행 수: {len(q):,}", ""]
    L += ["## 구성", "",
          f"- 등록(1) {int((e['status']=='1').sum()):,} / 탈퇴(2) {int((e['status']=='2').sum()):,}",
          f"- 법인(1) {int((e['type_code']=='1').sum()):,} / 개인(2) {int((e['type_code']=='2').sum()):,}",
          f"- 가입자 수 합계: {int(e['subscribers'].sum()):,} (※ 전체 근로자 수 아님)",
          f"- 검색 노출(등록·3명 이상): {int(e['search_visible'].sum()):,} / 연봉 추정 공개(10명 이상·계산 가능): {len(pub):,}",
          f"- 가입자 3명 미만 행: {int((e['subscribers']<3).sum()):,} (공식 공개 범위는 법인 3인 이상·개인 10인 이상)", ""]
    L += ["## 경고 플래그 건수(전체 행)", "", "| 플래그 | 건수 |", "|---|---|"]
    fl = e["flags"].str.split("|").explode()
    for k, v in fl[fl != ""].value_counts().items():
        L.append(f"| {k} | {v:,} |")
    L += ["", "## 품질 등급 (공개 대상 사업장 기준)", "", pub["grade"].value_counts().sort_index().to_string(), ""]
    L += ["## 상한 접근", "",
          f"- 공개 대상 중 cap_ratio≥0.9: {int(pub['cap_flag'].sum()):,} ({pub['cap_flag'].mean()*100:.2f}%)",
          f"- 공개 대상 중 상한 초과 이상(cap_ratio>1.01): {int((pub['cap_ratio']>1.01).sum()):,}", ""]
    qs = pub["est_annual"].quantile([.05, .25, .5, .75, .95, .99])
    L += ["## 연환산 추정금액 분포 (공개 대상, 원)", "", "| 분위 | 값 |", "|---|---|"]
    for k, v in qs.items():
        L.append(f"| {k:.0%} | {v:,.0f} |")
    L += ["", f"- 평균 {pub['est_annual'].mean():,.0f} / 최소 {pub['est_annual'].min():,.0f} / 최대 {pub['est_annual'].max():,.0f}", ""]
    g = pub.groupby(pd.cut(pub["subscribers"], [9, 29, 99, 299, 999, 10**7], labels=["10-29", "30-99", "100-299", "300-999", "1000+"]), observed=True)
    L += ["## 규모별 상한 접근 비중과 추정 중앙값", "", "| 규모 | 사업장 | cap≥0.9 비중 | 중앙값(원) |", "|---|---|---|---|"]
    for k, s in g:
        L.append(f"| {k} | {len(s):,} | {s['cap_flag'].mean()*100:.2f}% | {s['est_annual'].median():,.0f} |")
    L += ["", "## 한계", "",
          "- 이전 달 자료가 없어 전월 대비 변화, 12개월 지표는 계산하지 않음(미완료).",
          "- 가입자수는 '고지인원 포함'이라고만 공식 설명되어 있어, 고지 대상과 가입자 집계 범위의 일치 여부는 미확인 → 납부예외자 등이 분모에 섞이면 추정이 낮아질 수 있음.",
          "- 공시 급여(DART)와의 비교는 Stage 2 에서 수행(미완료)."]
    (ROOT / f"reports/quality/{ym}.md").write_text("\n".join(L), encoding="utf-8")


def benchmark_report(est, ym):
    cfg = yaml.safe_load(open(CONFIG_DIR / "benchmarks.yaml", encoding="utf-8"))["companies"]
    L = [f"# 주요 10개 기업 사업장 검색 — {ym}", "",
         "※ 정규화한 사업장명이 **완전 일치**하는 사업장만 표시. 법인 매칭은 Stage 2 이후이므로 합산하지 않음.",
         "※ 국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다. 표의 금액은 기준소득월액 연환산(상한 적용 후)입니다.", ""]
    for c in cfg:
        ex = est[est["name_norm"].isin([x.upper() for x in c["exact"]])]
        pre = est[est["name_norm"].str.startswith(tuple(x.upper() for x in c["exact"])) & ~est.index.isin(ex.index)]
        L += [f"## {c['label']}", "", f"- 완전 일치 사업장 {len(ex)}곳 / 이름이 같은 말로 시작하는 다른 후보 {len(pre)}곳(미표시·미합산)", ""]
        if ex.empty:
            L += ["- 완전 일치 없음 → 계산 불가(미확인)", ""]
            continue
        L += ["| 원본 사업장명 | 상태 | 소재지 | 가입자 수 | 당월고지금액 | 적용 요율 | 평균 기준소득월액 | 연환산 추정 | 상한 접근도 | 경고 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in ex.sort_values("subscribers", ascending=False).head(8).iterrows():
            L.append(f"| {r['name_raw']} | {'등록' if r['status']=='1' else '탈퇴'} | {r['addr_jibun']} | {r['subscribers']:,} | {r['bill_amount']:,} | "
                     f"{r['rate']*100:.1f}% | {won(r['est_monthly_income'])} | {won(r['est_annual'])} | "
                     f"{'—' if pd.isna(r['cap_ratio']) else f'{r['cap_ratio']:.3f}'} | {r['flags'] or '—'} |")
        if len(ex) > 8:
            L.append(f"\n(상위 8곳만 표시, 전체 {len(ex)}곳)")
        L.append("")
    (ROOT / f"reports/benchmarks/top10_{ym}.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
