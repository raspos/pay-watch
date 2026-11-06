"""PHASE 14.2 사람인 평균연봉 내보내기(공개 빌드용, 설정으로 켜고 끈다). 새 크롤링 없음 — saramin-experiment/data 의 인수 파일만 읽는다(그 프로젝트는 수정하지 않는다).
입력: paywatch_integrated_final.csv(기업 식별·매칭 판정), saramin_all_enterprises.csv(사람인 원본값, csn 로 연결), unverified_isolated.json(격리 2곳, 색인에서 제외).
공개 출력(site/data, 서비스에 필요한 최소 정보만): pay/s/<샤드>.json {id:{v:사람인 평균연봉(원), y:표시연도}}, finder/sm_entities.json(사람인에만 있는 기업의 이름·식별자 행).
내부 감사(저장소 reports/, site/ 로 복사 안 함): phase14_2_rep_selection.csv, phase14_2_match_audit.csv, phase14_2_summary.json — 매칭 근거·검증 결과·대표값 선택 이유.
식별자: DART 법인코드 8자리 유지, 사람인 전용 기업은 사람인 csn 의 해시로 만든 공개 id('S'+10자리 16진수; DART 코드를 만들지 않는다), 국민연금 사업장 ID 는 기존 그대로.
매칭 채택 규칙: 공식 별칭 사전 일치·정규화 이름 1:1 일치(식별자 직접 일치가 아님)만 DART 법인에 연결하고, 교차검증(값 비율)에서 크게 어긋나면 연결을 보류한다. 계열사·신규는 사람인 전용 기업으로 따로 둔다(모회사와 병합하지 않음).
config/publish.yaml 의 saramin_in_site 가 false 면 사람인 파일을 만들지 않고 기존 파일도 지운다. 실행: python -I -X utf8 pipeline/build_saramin.py"""
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
SRC = ROOT.parent / "saramin-experiment" / "data"
SITE_DATA = ROOT / "site/data"
SHARDS = 64
RATIO_LO, RATIO_HI = 1 / 3, 3.0            # 사람인/DART 값 비율이 이 범위를 벗어나면 식별 의심(연결 보류)
NPS_LO, NPS_HI = 1 / 3, 4.0                # DART 가 없을 때 국민연금 추정(상한 절단 하한값) 대비 비율 범위(참고 검증)
ACCEPT_EVIDENCE = ("OFFICIAL_ALIAS_MATCH", "NORMALIZED_NAME_EXACT_1TO1")
MARKS = re.compile(r"주식회사|유한회사|유한책임회사|합자회사|합명회사|㈜|㈔|\(주\)|\(유\)|\(사\)|\(합\)")


def normalize(s: str) -> str:                      # web/js/finder-core.js normalize 와 같은 규칙
    return re.sub(r"[^0-9a-zㄱ-ㆎ가-힣]", "", MARKS.sub("", unicodedata.normalize("NFKC", str(s)).lower()))


def sm_id(csn: str) -> str:
    return "S" + hashlib.sha1(csn.encode("utf-8")).hexdigest()[:10]


def shard_of(pid: str) -> int:                     # web/js/saramin.js shardKey 와 같은 규칙
    return int(pid) % SHARDS if re.fullmatch(r"\d{8}", pid) else int(pid[1:7], 16) % SHARDS


def config() -> dict:
    cfg = {}
    for line in Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml")).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-z_]+):\s*(\S+)\s*$", line.split("#")[0].rstrip() + " ")
        if m:
            cfg[m.group(1)] = m.group(2)
    return cfg


def remove_outputs() -> None:
    shutil.rmtree(SITE_DATA / "pay", ignore_errors=True)
    (SITE_DATA / "finder/sm_entities.json").unlink(missing_ok=True)


def build() -> dict:
    cfg = config()
    if cfg.get("saramin_in_site") != "true":
        remove_outputs()
        return {"saramin_in_site": False}
    import audit_dart_display as aud
    d = pd.read_csv(SRC / "paywatch_integrated_final.csv", encoding="utf-8-sig", dtype=str)
    raw = pd.read_csv(SRC / "saramin_all_enterprises.csv", encoding="utf-8-sig", dtype=str)
    raw["csn"] = raw.source_url.str.extract(r"csn=([^&]+)")[0]
    assert raw.csn.is_unique and raw.csn.notna().all()
    raw_val = dict(zip(raw.csn, raw.average_salary.astype(float)))
    raw_year = dict(zip(raw.csn, raw.salary_year))
    iso = {r["saramin_company_id"] for r in json.load(open(SRC / "unverified_isolated.json", encoding="utf-8"))}
    states, _ = aud.audit()
    st = states.set_index("corp_code")
    shard_recs = {}
    for p in (SITE_DATA / "corp").glob("*.json"):
        shard_recs.update(json.loads(p.read_text(encoding="utf-8")))
    only = json.loads((SITE_DATA / "finder/dart_only.json").read_text(encoding="utf-8"))
    dart_val = {c: r["dart"]["avg"] for c, r in shard_recs.items() if r.get("dart") and r["dart"].get("level") == "ok"}
    dart_val.update({c: v["avg"] for c, v in only.items()})
    nps_est = {c: r["nps"]["est"] for c, r in shard_recs.items() if r.get("nps") and r["nps"].get("est")}
    grades = pd.read_csv(ROOT / "reports/wage_model/phase12_firm_grades.csv", encoding="utf-8-sig")
    dart_names = {normalize(n) for n in grades.기업명} | {normalize(x) for x in d[d.dart_corp_code.notna()].display_name}
    assert not set(d.saramin_company_id.dropna()) & iso, "격리 기업이 통합 데이터에 있음"
    rows, audit, ent = [], [], []
    seen_names: dict[str, str] = {}
    for r in d.itertuples():
        csn = r.saramin_company_id
        if pd.isna(csn):
            continue
        v = raw_val[csn]
        yr = raw_year[csn]
        if r.salary_source == "SARAMIN_ESTIMATE":
            assert abs(v - float(r.average_salary)) < 1, f"사람인 원본값 불일치 {r.company_id}"
        a = {"company_id": r.company_id, "dart": r.dart_corp_code if pd.notna(r.dart_corp_code) else "", "csn": csn, "name": r.display_name, "evidence": r.match_evidence, "saramin_won": int(v), "year": yr}
        if pd.notna(r.dart_corp_code):                                  # DART 법인에 연결된 사람인 값
            c = r.dart_corp_code
            if r.match_evidence not in ACCEPT_EVIDENCE:
                a.update(decision="reject", reason="evidence_not_accepted")
            elif c in dart_val and not (RATIO_LO <= v / dart_val[c] <= RATIO_HI):
                a.update(decision="quarantine", reason=f"ratio_vs_dart={v / dart_val[c]:.2f}")
            elif c not in dart_val and c in nps_est and not (NPS_LO <= v / nps_est[c] <= NPS_HI):
                a.update(decision="quarantine", reason=f"ratio_vs_nps={v / nps_est[c]:.2f}")
            else:
                a.update(decision="accept", reason="crosscheck_dart" if c in dart_val else ("crosscheck_nps" if c in nps_est else "no_crosscheck"))
            if a["decision"] == "accept":
                rows.append((c, int(v), yr))
        else:                                                           # 사람인 전용 기업(신규·계열사): DART 코드를 만들지 않고 사람인 csn 해시를 공개 id 로 쓴다
            n = normalize(r.display_name) or normalize(r.legal_name)
            if n in dart_names:
                a.update(decision="quarantine", reason="name_collision_with_dart")
            elif n in seen_names:
                a.update(decision="quarantine", reason="name_collision_among_saramin")
            else:
                seen_names[n] = csn
                pid = sm_id(csn)
                a.update(decision="accept", reason="saramin_only", public_id=pid)
                rows.append((pid, int(v), yr))
                ent.append([pid, r.legal_name, r.display_name, "", 8 | 16, 0])
        audit.append(a)
    # 이름이 겹친 사람인 전용 기업은 먼저 들어온 쪽도 모호하므로 함께 격리한다
    clash = {normalize(x["name"]) for x in audit if x.get("reason") == "name_collision_among_saramin"}
    bad = set()
    for x in audit:
        if x.get("decision") == "accept" and x.get("reason") == "saramin_only" and normalize(x["name"]) in clash:
            x.update(decision="quarantine", reason="name_collision_among_saramin")
            bad.add(x["public_id"])
    rows = [t for t in rows if t[0] not in bad]
    ent = [e for e in ent if e[0] not in bad]
    # 공개 출력
    shutil.rmtree(SITE_DATA / "pay", ignore_errors=True)
    out = SITE_DATA / "pay/s"
    out.mkdir(parents=True)
    shards = {i: {} for i in range(SHARDS)}
    for pid, v, yr in rows:
        shards[shard_of(pid)][pid] = {"v": v, "y": int(yr)}
    for i, s in shards.items():
        (out / f"{i}.json").write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ent.sort(key=lambda e: e[0])
    (SITE_DATA / "finder/sm_entities.json").write_text(json.dumps(ent, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # 대표값 선택 기록(내부): 모든 DART 법인과 사람인 전용 기업
    sm_by_dart = {c: v for c, v, _ in rows if re.fullmatch(r"\d{8}", c)}
    sel = []
    for code, s in st.state.items():
        if s in ("shown_page", "shown_dart_only"):
            src, why = "dart", "dart_valid"
        elif code in sm_by_dart:
            src, why = "saramin", ("dart_missing" if s == "no_dart" else "dart_held_quality")
        else:
            src, why = "none", "no_source"
        sel.append({"id": code, "kind": "dart", "dart_state": s, "rep_source": src, "reason": why, "dart_won": dart_val.get(code, ""), "saramin_won": sm_by_dart.get(code, "")})
    for pid, v, yr in rows:
        if pid.startswith("S"):
            sel.append({"id": pid, "kind": "saramin_only", "dart_state": "", "rep_source": "saramin", "reason": "saramin_only", "dart_won": "", "saramin_won": v})
    rep = pd.DataFrame(sel)
    aud_df = pd.DataFrame(audit)
    rep.to_csv(ROOT / "reports/phase14_2_rep_selection.csv", index=False, encoding="utf-8-sig")
    aud_df.to_csv(ROOT / "reports/phase14_2_match_audit.csv", index=False, encoding="utf-8-sig")
    aud_df["reason_kind"] = aud_df.reason.str.replace(r"=.*", "", regex=True)
    summary = {"integrated_rows": len(d), "isolated_excluded": len(iso), "entities_total": int(len(rep)), "rep_source": rep.rep_source.value_counts().to_dict(),
               "rep_reason": rep.reason.value_counts().to_dict(), "decisions": aud_df.decision.value_counts().to_dict(),
               "decision_reasons": {f"{k[0]}:{k[1]}": int(v) for k, v in aud_df.groupby(["decision", "reason_kind"]).size().items()},
               "saramin_only_entities": len(ent), "dart_linked_accepted": len(sm_by_dart), "provided_total": int((rep.rep_source != "none").sum())}
    (ROOT / "reports/phase14_2_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=1))
