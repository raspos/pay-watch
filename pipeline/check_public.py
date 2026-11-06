"""배포 전 공개 검사(site/ 만 대상). 실패하면 종료 코드 1. 연구용 자료가 공개 파일에 섞였는지를 파일 이름과 내용 전체에서 확인한다.
- 연구용 파일·폴더(exp*, data/exp, preview 표식, 연구 CSV·보고서)가 없다.
- 사람인 데이터는 설정(saramin_in_site)으로만 포함되고 최소 필드만 있으며, saramin_permission 이 confirmed 가 아니면 종료 코드 2 로 배포를 차단한다.
- 기업별 근속 추정 범위·내부 품질 등급·사람인 데이터·연구용 문구가 없다.
- 공개 데이터 정책: 공시 급여 원자료의 정합성이 확인되지 않은 기업만 보류하고, 모형 품질만 문제인 기업의 공시값은 숨기지 않는다. 평균근속 45년 초과는 공개하지 않는다.
- 통합 검색 색인은 이름·식별자·자료 유무 표시만 담는다.
- 공개 추정 데이터(data/est)는 publish_estimates=true 일 때만 존재하며 최소 필드(b,x,cau,w)만 담는다(내부 등급 글자·공시 평균 없음).
실행: python -I -X utf8 pipeline/check_public.py"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("PAYWATCH_SITE_DIR", ROOT / "site"))      # 번들 검증용 경로(기본은 site/)
CFG = Path(os.environ.get("PAYWATCH_PUBLISH_CONFIG", ROOT / "config/publish.yaml"))      # 테스트용 설정 경로(기본은 저장소 설정)
sys.path.insert(0, str(ROOT / "pipeline"))

BAD_NAME = re.compile(r"(^|/)(exp[-_.]|preview|phase\d|reports?/|.*grade|.*사람인|.*integrated)", re.I)
# 파일 내용 표식: 연구용 화면·문구·데이터 필드. (공개 JS 의 pay-source.js 는 소스 id 'saramin' 자리만 가지며 데이터는 없다 — JS 는 사람인 검사에서 제외)
BAD_TEXT = ["PAY WATCH LAB 실험적 추정", "LAB 실험", "data/exp", "exp-embed", "exp-section", "exp-core", "PREVIEW_ONLY", "공개 적합성", "phase12_", "실험적 추정"]
BAD_DATA_TEXT = ["공개 적합성", "형태실험", "[신규]", "phase12", "exp_range", "saramin.co.kr", "SARAMIN_", "csn=", "match_evidence", "quality_status", "saramin_company_id", "paywatch_integrated"]    # 사람인 원본 URL·내부 매칭/품질 필드·통합 데이터셋 이름이 공개 데이터에 있으면 안 된다


EST_ON = re.search(r"^publish_estimates:\s*true", CFG.read_text(encoding="utf-8"), re.M) is not None


def check_est(site: Path, fails: list) -> None:
    """공개 추정 데이터(data/est): 설정이 켜져 있을 때만 존재, 최소 필드만, 범위 형식·포함 관계 정상, DART 코드 형식."""
    est = site / "data/est"
    if not est.exists():
        if EST_ON:
            fails.append("publish_estimates=true 인데 data/est 가 없음(pipeline/export_est_public.py)")
        return
    if not EST_ON:
        fails.append("publish_estimates=false 인데 data/est 파일이 site/ 에 있음")
        return
    n = 0
    for f in (est / "s").glob("*.json"):
        for code, r in json.loads(f.read_text(encoding="utf-8")).items():
            n += 1
            ok = re.fullmatch(r"\d{8}", code) and set(r) <= {"b", "x", "cau", "w", "y", "m"} and {"b", "cau", "y", "m"} <= set(r) and r["y"] == 2025
            rng = lambda v: isinstance(v, list) and len(v) == 5 and all(isinstance(t, list) and len(t) == 2 and all(isinstance(u, int) for u in t) and 0 < t[0] <= t[1] for t in v)
            ok = ok and rng(r["b"]) and (r.get("x") is None or (rng(r["x"]) and all(x[0] <= b[0] and x[1] >= b[1] for x, b in zip(r["x"], r["b"]))))
            if not ok:
                fails.append(f"공개 추정 데이터 형식 이상(허용 필드 b,x,cau,w,y,m 외 포함·범위 이상): {code}")
                return
    if n == 0:
        fails.append("공개 추정 데이터가 비어 있음")
    meta = est / "meta.json"
    if not meta.exists() or json.loads(meta.read_text(encoding="utf-8")).get("firms") != n:
        fails.append("est/meta.json 없음 또는 기업 수 불일치")
    # 입력인 공시 평균급여가 보류된 기업(level != ok)의 추정은 공개하지 않는다
    held = set()
    for f in (site / "data/corp").glob("*.json"):
        for code, r in json.loads(f.read_text(encoding="utf-8")).items():
            if r.get("hold") or (r.get("dart") and r["dart"].get("level") != "ok"):
                held.add(code)
    bad = [c for f in (est / "s").glob("*.json") for c in json.loads(f.read_text(encoding="utf-8")) if c in held]
    if bad:
        fails.append(f"급여 정합성 보류 기업 {len(bad)}곳의 추정이 공개됨 예 {bad[:3]}")


def main() -> int:
    fails: list[str] = []
    files = [p for p in SITE.rglob("*") if p.is_file()]
    for p in files:
        rel = p.relative_to(SITE).as_posix()
        if BAD_NAME.search(rel):
            fails.append(f"연구용으로 보이는 파일 이름: {rel}")
        if p.suffix in (".html", ".js", ".css", ".json", ".txt", ".md", ".csv"):
            t = p.read_text(encoding="utf-8", errors="ignore")
            for bad in [b for b in BAD_TEXT if not (EST_ON and b == "실험적 추정")]:      # 추정 영역을 공개하는 설정이면 화면 라벨 '실험적 추정'은 허용
                if bad in t:
                    fails.append(f"{rel}: 연구용 표식 '{bad}'")
            if rel.startswith("data/"):
                for bad in BAD_DATA_TEXT:
                    if bad in t:
                        fails.append(f"{rel}: 공개 데이터에 금지 표식 '{bad}'")
        if p.suffix in (".csv", ".parquet", ".xlsx"):
            fails.append(f"공개 폴더에 데이터 파일: {rel}")
    # 공개 데이터 정책(PHASE 14.1): 공시 급여 원자료의 정합성이 확인되지 않는 기업만 보류, 모형 품질 때문에 공시값을 숨기지 않는다. 평균근속 45년 초과는 공개하지 않는다.
    import apply_public_policy as pol
    recs = {}
    for f in (SITE / "data/corp").glob("*.json"):
        recs.update(json.loads(f.read_text(encoding="utf-8")))
    man = json.loads(Path(os.environ.get("PAYWATCH_POLICY_MANIFEST", ROOT / "config/public_policy_manifest.json")).read_text(encoding="utf-8"))   # 원자료 캐시가 없는 환경(CI)에서도 검사할 수 있도록 apply_public_policy 가 남긴 기록
    if (ROOT / "data/raw/dart/cache").exists() and not os.environ.get("PAYWATCH_SKIP_RAW_CHECK"):    # 원자료가 있으면 기록이 원자료와 일치하는지도 확인(테스트는 속도를 위해 건너뜀)
        emp = pol.emp_table(); real_held = sorted(c for c in pol.doubt_codes() if not (emp.get(c) is not None and pol.consistent(emp[c])))
        if real_held != man["held"]:
            fails.append("공개 정책 기록(config/public_policy_manifest.json)이 원자료와 다름: apply_public_policy.py 재실행 필요")
    for code in man["restored"]:
        rec = recs.get(code)
        if rec is not None and (not rec.get("dart") or rec.get("hold")):
            fails.append(f"급여 정합성이 확인된 기업 {code} 의 공시 평균급여가 복원되지 않음")
    for code in man["held"]:
        rec = recs.get(code)
        if rec is not None and (rec.get("dart") is not None or not rec.get("hold")):
            fails.append(f"급여 원자료 정합성 문제 기업 {code} 의 공시 평균급여가 숨겨지지 않음")
    for code, rec in recs.items():
        d = rec.get("dart")
        if d and d.get("level") != "ok" and (d.get("avg") is not None or d.get("total") is not None or "consistency" in d):
            fails.append(f"급여 정합성 문제로 보류된 기업 {code} 의 공시 급여 원본값(avg·total·consistency)이 공개 JSON 에 있음")
        if d and d.get("tenure") is not None and d["tenure"] > pol.TENURE_MAX:
            fails.append(f"평균근속 {d['tenure']}년(45년 초과)이 공개됨: {code}")
    fo = SITE / "data/finder/dart_only.json"
    if fo.exists():
        only = json.loads(fo.read_text(encoding="utf-8"))
        if any(set(v) != {"fy", "employees", "avg", "tenure", "level", "stlm", "src"} or v["level"] != "ok" for v in only.values()) or set(only) & set(recs) or len(only) != man["dart_only"]:
            fails.append("dart_only.json 형식 이상(상세 페이지가 있는 기업이 섞였거나 필드가 다름)")
    # 통합 검색 색인: 이름·식별자·플래그만
    fe = SITE / "data/finder/entities.json"
    if fe.exists():
        rows = json.loads(fe.read_text(encoding="utf-8"))
        if not all(len(r) == 6 and re.fullmatch(r"\d{8}|S[0-9a-f]{10}", r[0]) and isinstance(r[4], int) and 0 <= r[4] <= 31 for r in rows):
            fails.append("통합 검색 색인 행 형식 이상(이름·식별자·플래그 외 필드가 있음)")
    else:
        fails.append("통합 검색 색인 없음(pipeline/build_finder.py)")
    # 사람인 데이터 게이트(PHASE 14.2): 포함은 설정으로만, 게시·재배포 권한이 확인되기 전에는 배포 차단(종료 코드 2)
    cfgtxt = CFG.read_text(encoding="utf-8")
    sm_in = re.search(r"^saramin_in_site:\s*true", cfgtxt, re.M) is not None
    sm_ok = re.search(r"^saramin_permission:\s*confirmed", cfgtxt, re.M) is not None
    sm_present = (SITE / "data/pay").exists() or (SITE / "data/finder/sm_entities.json").exists()
    blocked = False
    if sm_present and not sm_in:
        fails.append("saramin_in_site=false 인데 사람인 데이터 파일이 site/ 에 있음(pipeline/build_saramin.py 재실행)")
    if sm_present:
        for f in (SITE / "data/pay/s").glob("*.json"):
            for pid, v in json.loads(f.read_text(encoding="utf-8")).items():
                if set(v) != {"v", "y"} or not re.fullmatch(r"\d{8}|S[0-9a-f]{10}", pid):
                    fails.append(f"사람인 공개 데이터 형식 이상(최소 필드 v,y 외 포함): {f.name}")
                    break
        if not sm_ok:
            blocked = True
    check_est(SITE, fails)
    # 정책 설정
    cfg = CFG.read_text(encoding="utf-8")
    if not (SITE / "robots.txt").exists():
        fails.append("robots.txt 없음")
    print(f"공개 검사: 파일 {len(files)}개, 실패 {len(fails)}건")
    for f in fails[:30]:
        print(" -", f)
    if fails:
        return 1
    if blocked:
        print("배포 차단: site/ 에 사람인 데이터가 있으나 saramin_permission 이 confirmed 가 아님(외부 게시·재배포 권한 미확인). 데이터 누출은 없음 — 종료 코드 2")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
