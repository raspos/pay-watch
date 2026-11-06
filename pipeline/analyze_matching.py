"""캐시된 DART 기업개황만으로 NPS(2026-09) 사업장과의 매칭 품질을 분석한다. 네트워크 호출 없음."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.company_matcher import addr_key, load_company_cache, match  # noqa: E402
from paywatch.dart_client import CACHE, ROOT  # noqa: E402
from paywatch.load_nps import normalize_alias, normalize_name  # noqa: E402

YM = "2026-09"


def validity():
    files = sorted((CACHE / "company").glob("*.json"))
    rows = []
    for p in files:
        j = json.loads(p.read_text(encoding="utf-8"))
        b = (j.get("bizr_no") or "").replace("-", "")
        rows.append({"file_corp": p.stem.split("_")[0], "status": j.get("status"), "bizr_ok": b.isdigit() and len(b) == 10,
                     "has_addr": bool((j.get("adres") or "").strip()), "has_jurir": bool((j.get("jurir_no") or "").strip()),
                     "listed": bool(j.get("stock_code")), "corp_cls": j.get("corp_cls"), "induty": bool(j.get("induty_code")),
                     "name": j.get("corp_name")})
    return pd.DataFrame(rows), len(files)


def main():
    v, nfiles = validity()
    d = load_company_cache()
    cc = pd.read_parquet(ROOT / "data/interim/dart_corp_list.parquet")
    tgt = pd.read_parquet(ROOT / "data/interim/dart_targets.parquet")
    L = ["# Stage 2 중간 리포트 — 캐시된 DART 기업개황 × NPS " + YM, "",
         "※ 수집이 중단되어 **상장사 가입자 상위 일부 1,000건**만 대상이다. 편향된 표본이므로 아래 비율은 전체 모집단의 매칭 성공률이 아니다.", ""]
    L += ["## 1. 캐시 유효성", "",
          f"- 캐시 파일 {nfiles}건 / status=000 {int((v.status=='000').sum())}건 / 파일명 corp_code 가 고유번호 목록에 존재 {int(v.file_corp.isin(cc.corp_code).sum())}건",
          f"- 사업자등록번호 10자리 숫자 {int(v.bizr_ok.sum())}건 / 주소 있음 {int(v.has_addr.sum())} / 법인등록번호 있음 {int(v.has_jurir.sum())} / 업종코드 있음 {int(v.induty.sum())}",
          f"- 상장(종목코드 있음) {int(v.listed.sum())}건 / 법인구분 {v.corp_cls.value_counts().to_dict()}",
          f"- 파일명 중복 corp_code: {int(v.file_corp.duplicated().sum())}건 / 수집 대상 목록(`dart_targets`) 중 앞 1,000건과 일치: "
          f"{int(set(v.file_corp)==set(tgt.corp_code.head(len(v))))}", ""]

    est = pd.read_parquet(ROOT / f"data/interim/nps_{YM}.parquet")
    ids = pd.read_parquet(ROOT / f"data/interim/ids_{YM}.parquet")
    est = est.join(ids[["wp_id"]])
    act = est[(est.status == "1") & (est.subscribers >= 3)].copy()
    d["nn"] = d.corp_name.map(normalize_name)
    d["bizr6"] = d.bizr_no.str[:6]

    # --- 사업장 중심: 이름이 DART 캐시와 같은 사업장만 매칭 판정 ---
    d["na"] = d.nn.map(normalize_alias)
    cand = act[act.name_norm.isin(set(d.nn)) | act.name_norm.map(normalize_alias).isin(set(d.na))]
    res = match(cand, d)
    res = res.merge(cand[["wp_id", "name_raw", "subscribers", "est_annual", "cap_ratio", "addr_jibun"]], on="wp_id")
    L += ["## 2. 사업장 중심 매칭 (NPS 등록·가입자 3명 이상 사업장 중 이름이 캐시 법인과 같은 것)", "",
          f"- 대상 사업장 {len(cand):,}곳", "", "| 등급 | 사업장 | 가입자 합 |", "|---|---|---|"]
    for g, s in res.groupby("grade"):
        L.append(f"| {g} | {len(s):,} | {int(s.subscribers.sum()):,} |")
    L += ["", "근거(evidence) 분포:", ""]
    for k, c in res.evidence.value_counts().items():
        L.append(f"- {k}: {c:,}")

    # --- 법인 중심 ---
    m = res[res.corp_code.notna()]
    by = m.groupby("corp_code").agg(wps=("wp_id", "size"), subs=("subscribers", "sum"), top=("score", "max"))
    lab = {5: "high_confidence(이름+번호6+시군구)", 4: "candidate(이름+번호6, 주소 불일치)", 3: "candidate(음역 이름+번호6)",
           2: "candidate(이름만, 번호6 불일치)"}
    corp_grade = pd.Series("no_nps_candidate", index=d.corp_code)
    corp_grade.loc[by.index] = by["top"].map(lab)
    amb = res[res.grade == "ambiguous"]
    L += ["", "## 3. 법인 중심 (캐시 1,000개 법인 기준)", "", "| 결과 | 법인 수 |", "|---|---|"]
    for k, c in corp_grade.value_counts().items():
        L.append(f"| {k} | {c} |")
    L.append(f"\n- 이름은 같지만 사업자번호6 불일치로 제외된 사업장: {int((res.evidence=='name_match_brn6_mismatch').sum()):,}곳")
    L.append(f"- 후보가 둘 이상 법인에 걸려 ambiguous 인 사업장: {len(amb):,}곳")

    # --- 법인 분할: 한 법인에 매칭된 사업장 수 ---
    hc = res[res.grade == "high_confidence"]
    per = hc.groupby("corp_code").size()
    L += ["", "## 4. 법인 분할 (high_confidence 사업장 수 / 법인)", "",
          f"- high_confidence 법인 {per.size}개, 사업장 1곳 {int((per==1).sum())}개, 2곳 이상 {int((per>1).sum())}개, 최대 {int(per.max()) if per.size else 0}곳"]
    L += ["- 같은 법인의 사업장끼리도 주소(시군구)가 다를 수 있어 위 등급은 '이름+사업자번호6+시군구'가 모두 맞는 사업장만 high_confidence 로 본다."]

    # --- 실패 사례: 이름이 캐시와 다르지만 사업자번호6 일치 + 주소 일치 (이름 표기 차이 후보) ---
    nm_miss = d[~d.nn.isin(set(act.name_norm))]
    L += ["", "## 5. 매칭 실패 분석", "",
          f"- 캐시 법인 중 NPS 등록·3명 이상 사업장 중에 정규화명이 같은 곳이 **없는** 법인: {len(nm_miss)}개"]
    fails = []
    brn_index = act.groupby("brn6")
    for _, r in nm_miss.iterrows():
        if r.bizr6 in brn_index.groups:
            g = act.loc[brn_index.groups[r.bizr6]]
            ak = addr_key(r.adres)
            g = g[g.addr_jibun.map(addr_key) == ak] if ak else g.iloc[0:0]
            if len(g):
                fails.append((r.corp_name, r.bizr_no, "; ".join(g.name_raw.head(3)), int(g.subscribers.sum())))
    L += [f"- 그중 사업자번호6 + 시군구가 같은 NPS 사업장이 있어 '표기 차이 후보'인 법인: {len(fails)}개 (자동 매칭하지 않음, 수동 검토 대상)", ""]
    if fails:
        L += ["| DART 법인명 | DART 사업자번호 | NPS 사업장명 후보 | 가입자 합 |", "|---|---|---|---|"]
        for f in fails[:25]:
            L.append(f"| {f[0]} | {f[1][:6]}**** | {f[2]} | {f[3]:,} |")
    # 이름만 같고 번호가 다른 사례(오매칭 위험)
    risk = res[res.score == 2].sort_values("subscribers", ascending=False).head(15)
    L += ["", "### 이름만 일치하고 사업자번호6 이 다른 사례 (공장·지점일 수도, 동명 타사일 수도 있음 → 합산 제외)", "", "| NPS 사업장 | 가입자 | NPS 소재지 |", "|---|---|---|"]
    for _, r in risk.iterrows():
        L.append(f"| {r['name_raw']} | {r['subscribers']:,} | {r['addr_jibun']} |")

    (ROOT / "reports/matching").mkdir(parents=True, exist_ok=True)
    out = ROOT / "reports/matching/stage2_cache_match.md"
    out.write_text("\n".join(L), encoding="utf-8")
    res.to_parquet(ROOT / "data/interim/match_cache_sample.parquet")
    print(out)


if __name__ == "__main__":
    main()
