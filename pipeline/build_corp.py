"""법인 레이어 빌드: 매칭 → 법인 합산 → site/data/corp/*.json, 사업장 상세에 법인 연결(co) 추가, 검증 리포트.
네트워크 호출 없음(DART 캐시만 사용). export_json.py 다음에 실행한다."""
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.company_matcher import load_company_cache, load_overrides, match  # noqa: E402
from paywatch.corp_layer import CONFIRMED, CONSISTENCY_OK, build_corp_records, load_emp_table  # noqa: E402
from paywatch.export_public import scrub, write_json  # noqa: E402
from paywatch.metrics import load_panel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data/interim"
SITE = ROOT / "site/data"
CORP_SHARDS = 128
BENCH = {"삼성전자": "삼성전자", "SK하이닉스": "에스케이하이닉스", "현대자동차": "현대자동차", "기아": "기아", "네이버": "네이버",
         "카카오": "카카오", "KB국민은행": "국민은행", "신한은행": "신한은행", "포스코": "포스코", "LG전자": "엘지전자"}


def pct(x, d=0):
    return "—" if x is None or pd.isna(x) else f"{x*100:.{d}f}%"


import time
_T0 = time.time()


def step(msg):
    print(f"[{time.time()-_T0:6.0f}s] {msg}", flush=True)


def main():
    ms = sorted(p.split("nps_")[1][:7] for p in glob.glob(str(INTERIM / "nps_20*.parquet")))
    t = ms[-1]
    step("패널 로딩")
    P = load_panel(INTERIM, ms)
    step("패널 완료")
    d = pd.read_parquet(INTERIM / f"metrics_{t}.parquet")
    est = pd.read_parquet(INTERIM / f"nps_{t}.parquet").join(pd.read_parquet(INTERIM / f"ids_{t}.parquet")[["wp_id"]])
    step("매칭 입력 로딩")
    comp = load_company_cache()
    emp = load_emp_table("2025")
    step(f"기업개황 {len(comp)}, 직원현황 {len(emp)}")
    ov = load_overrides()
    act = est[(est["status"] == "1") & (est["subscribers"] >= 3)]
    step("매칭 시작")
    res = match(act, comp, ov)
    step("매칭 완료")
    recs = build_corp_records(res, comp, emp, P, ms, d)
    nan_fields = sorted({k for r in recs for k, v in r.items() if isinstance(v, float) and v != v})
    step(f"NaN 필드(정리 대상): {nan_fields}")
    recs = [scrub(r) for r in recs]
    step(f"법인 레코드 {len(recs)}")

    # --- 공개 JSON: 법인 샤드 + 사업장→법인 연결
    shutil_rm = SITE / "corp"
    if shutil_rm.exists():
        import shutil
        shutil.rmtree(shutil_rm)
    shards = {}
    for r in recs:
        shards.setdefault(int(r["code"]) % CORP_SHARDS, {})[r["code"]] = r
    for k, v in shards.items():
        write_json(SITE / f"corp/{k}.json", v)
    link = {}
    for r in recs:
        for w in r["wps"]:
            link[w["id"]] = {"c": r["code"], "p": w["id"] == r["primary"]}
    conf = res[res["grade"].isin(CONFIRMED) & res["corp_code"].notna()]
    for w, c in zip(conf["wp_id"], conf["corp_code"]):          # wps 목록(상위 30)에 안 든 사업장도 연결
        link.setdefault(int(w), {"c": c, "p": False})
    bysh = {}
    for w, v in link.items():
        bysh.setdefault(w % 1024, {})[str(w)] = v
    patched = 0
    for sh, items in bysh.items():
        p = SITE / f"d/{sh}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for wid, v in items.items():
            if wid in data:
                data[wid]["co"] = v
                patched += 1
        write_json(p, data)
    meta = json.loads((SITE / "meta.json").read_text(encoding="utf-8"))
    meta["counts"]["corps"] = len(recs)
    meta["dart_fy"] = 2025
    write_json(SITE / "meta.json", meta)
    report(res, comp, emp, recs, act, d, t, patched)
    print("corps", len(recs), "workplaces linked", patched, "dart usable", int(emp["usable"].sum()) if len(emp) else 0)


def report(res, comp, emp, recs, act, d, ym, patched):
    L = [f"# Stage 2(개편) 법인 레이어 리포트 — NPS {ym} × DART FY2025", "",
         "※ 공시 1인 평균급여는 DART 직원현황의 급여총액÷직원수로 계산한 **파생값**이다. 국민연금 추정은 기준소득월액 역산 **추정값**이다. 두 값을 섞어 순위를 만들지 않는다.", ""]
    g = res["grade"].value_counts()
    L += ["## 1. 매칭 (등록·가입자 3명 이상 사업장 %s곳 중 이름 후보가 있는 곳)" % f"{len(act):,}", "",
          "| 등급 | 사업장 |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in g.items() if k != "unmatched"]
    ev = res[res["grade"].isin(["high_confidence", "verified"])]["evidence"].value_counts()
    L += ["", "근거 분포(확정 등급): " + ", ".join(f"{k} {v:,}" for k, v in ev.items()), ""]
    nconf = len(recs)
    ndata = sum(1 for r in recs if r["dart"])
    nok = sum(1 for r in recs if r["dart"] and r["dart"]["level"] == "ok")
    ncau = sum(1 for r in recs if r["dart"] and r["dart"]["level"] != "ok")
    nodata = emp.attrs.get("nodata", 0)
    L += ["## 2. 법인 단위 현황", "",
          f"- 확정(high_confidence/verified) 사업장이 있는 DART 법인: **{nconf:,}곳**",
          f"- 직원현황(FY2025 사업보고서) 응답: 데이터 있음 {len(emp):,}곳 / 없음(013) {nodata:,}곳 (조회한 법인 중 {nodata/max(1,len(emp)+nodata)*100:.0f}%는 해당 연도 직원현황이 없음)",
          f"- 급여 계산 가능(usable): {int(emp['usable'].sum()) if len(emp) else 0:,}곳 / 계산 불가: {int((~emp['usable']).sum()) if len(emp) else 0:,}곳",
          f"- 확정 법인 중 공시값 보유 {ndata:,}곳 → 일관성 통과(행별 평균과 총액÷인원 차이 5% 이하) **{nok:,}곳** / 주의·미검증 {ncau:,}곳",
          f"- 화면 대표 숫자 기준: 공시 {sum(1 for r in recs if r['basis']=='dart'):,}곳, 국민연금 추정 {sum(1 for r in recs if r['basis']=='nps'):,}곳",
          f"- 공시 비교집단 위치(상위 %) 계산: {sum(1 for r in recs if r['dart'] and r['dart']['pos']):,}곳 (비교집단 30곳 이상일 때만)", ""]
    if len(emp):
        b = emp[emp["usable"]]["basis"].value_counts()
        L += ["- 급여를 읽은 행 구분: " + ", ".join(f"{k} {v:,}" for k, v in b.head(6).items()), ""]
    # 범위·오차 분석
    rows = []
    for r in recs:
        if r["dart"] and r["dart"]["level"] == "ok" and r["nps"]["est"] and r["scope"] is not None:
            rows.append({"code": r["code"], "name": r["n"], "dart": r["dart"]["avg"], "nps": r["nps"]["est"], "cap": r["nps"]["cap"], "scope": r["scope"], "emp": r["dart"]["employees"]})
    a = pd.DataFrame(rows)
    L += ["## 3. 국민연금 추정 대 공시 평균급여", ""]
    if len(a):
        a["ratio"] = a["nps"] / a["dart"]
        comp_scope = a[(a["scope"] >= 0.7) & (a["scope"] <= 1.3)]
        L += [f"- 공시값(일관성 통과)과 NPS 합산값이 모두 있는 법인 {len(a):,}곳. 이 중 **범위가 비슷한 곳(확인 사업장 가입자 ÷ 공시 직원 수 0.7~1.3)** {len(comp_scope):,}곳만 오차 분석에 사용(나머지는 집계 범위가 달라 부적합).",
              f"- 범위 분포(전체): 25% {a['scope'].quantile(.25):.2f} / 중앙 {a['scope'].median():.2f} / 75% {a['scope'].quantile(.75):.2f}", ""]
        if len(comp_scope) >= 10:
            c = comp_scope.copy()
            c["cbin"] = pd.cut(c["cap"].fillna(0), [-1, .7, .9, .95, 10], labels=["<0.7", "0.7~0.9", "0.9~0.95", "≥0.95"])
            L += ["| 상한 접근도(NPS 합산) | 법인 | NPS÷공시 중앙값 | 25~75% | 절대상대오차 중앙값 |", "|---|---|---|---|---|"]
            for k, s in c.groupby("cbin", observed=True):
                L.append(f"| {k} | {len(s)} | {s['ratio'].median():.2f} | {s['ratio'].quantile(.25):.2f}~{s['ratio'].quantile(.75):.2f} | {(s['ratio']-1).abs().median()*100:.0f}% |")
            L += ["", f"- 전체: 중앙값 NPS÷공시 {c['ratio'].median():.2f}, 평균절대오차율 {(c['ratio']-1).abs().mean()*100:.0f}%, 중앙절대오차율 {(c['ratio']-1).abs().median()*100:.0f}%, NPS가 공시보다 낮은 법인 {(c['ratio']<1).mean()*100:.0f}%",
                  "- 해석 주의: 공시 급여에는 상여·성과급이 포함되고 기준소득월액에는 상한이 있어 NPS가 낮게 나오는 것이 정상이다. 이 분석은 **보정에 쓰지 않으며**(학습·검증 분리 전), 대표 숫자 선택 규칙의 근거로만 쓴다.", ""]
        else:
            L += ["- 범위가 비슷한 표본이 10곳 미만이라 오차 분포를 내지 않는다.", ""]
    else:
        L += ["- 비교 가능한 법인이 아직 없다.", ""]
    # 벤치마크
    byname = {r["n"]: r for r in recs}
    L += ["## 4. 주요 10개 기업", "", "| 기업 | 매칭 | 공시 1인 평균(파생) | 직원 | 근속 | 일관성 | NPS 합산 추정 | 상한 접근 | 범위 | 대표 숫자 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for lab, nn in BENCH.items():
        w = act[act["name_norm"] == nn].sort_values("subscribers", ascending=False).head(1)
        if w.empty:
            L.append(f"| {lab} | 사업장 없음 | | | | | | | | |")
            continue
        m = res[res["wp_id"] == w["wp_id"].iloc[0]].iloc[0]
        rec = next((r for r in recs if r["code"] == m["corp_code"]), None) if pd.notna(m["corp_code"]) else None
        if rec is None:
            L.append(f"| {lab} | {m['grade']} | 법인 연결 없음 | | | | NPS 사업장 {w['est_annual'].iloc[0]/1e4:,.0f}만원 | | | NPS(사업장) |")
            continue
        dt = rec["dart"]
        L.append(f"| {lab} | {m['grade']}({m['evidence']}) | {'—' if not dt else f'{dt['avg']/1e4:,.0f}만원'} | {'—' if not dt else f'{dt['employees']:,}'} | {'—' if not dt or dt['tenure'] is None else dt['tenure']} | {'—' if not dt else dt['level']} | "
                 f"{'—' if not rec['nps']['est'] else f'{rec['nps']['est']/1e4:,.0f}만원'} | {rec['nps']['cap']} | {rec['scope']} | {'공시' if rec['basis']=='dart' else 'NPS 추정'} |")
    # 수동 확정 검토 후보(큰 사업장 중 법인 연결이 없는 곳)
    un = act.merge(res[["wp_id", "grade", "corp_code", "evidence"]].rename(columns={"grade": "match_grade"}), on="wp_id")   # act 에도 품질 등급 grade 가 있어 이름 분리
    un = un[~un["match_grade"].isin(CONFIRMED)].sort_values("subscribers", ascending=False).head(60)
    cand = un[["name_raw", "subscribers", "addr_jibun", "match_grade", "evidence", "corp_code"]]
    cand.to_csv(ROOT / "reports/matching/override_review_candidates.csv", index=False, encoding="utf-8-sig")
    L += ["", "## 5. 수동 확정 검토 대상(가입자 큰 사업장 중 법인 연결이 확정되지 않은 곳 상위 60)", "",
          "`reports/matching/override_review_candidates.csv` 참고. 근거를 확인한 건만 `config/match_overrides.csv`에 사업자번호6·정규화명·DART 고유번호와 근거를 적어 확정한다.",
          f"- 매칭 등급 분포: {un['match_grade'].value_counts().to_dict()}", ""]
    (ROOT / "reports/matching/stage2_corp_layer.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
