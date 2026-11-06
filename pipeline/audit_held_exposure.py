"""급여 정합성 문제로 보류된 기업의 공시 급여 원본값(1인 평균·급여 총액)이 공개 JSON 어디에도 남아 있지 않은지 직접 확인한다(원자료 캐시 필요, 로컬 전용).
방법: 내부 원자료(직원현황 캐시)에서 보류 대상(급여 계산 가능 + 일관성 5% 초과 + 사람인·DART 표시 대상이 아님) 기업의 평균·총액 정수 값을 모으고, site/data 의 모든 JSON 에서 7자리 이상 정수 토큰과 대조한다.
숫자 우연 일치 가능성을 줄이기 위해 해당 기업 자신의 파일(법인 샤드)은 구조(필드 제거)로 따로 검사하고, 다른 파일에서 같은 숫자가 나오면 목록으로 보고한다.
실행: python -I -X utf8 pipeline/audit_held_exposure.py [--dirs corp finder pay ...]   (기본: data 전체)"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
TOKEN = re.compile(r"(?<![\d.])\d{7,}(?![\d.])")


def held_values() -> dict[int, str]:
    """보류 기업의 평균·총액(정수, 반올림·내림 모두) → 기업 코드."""
    import apply_public_policy as pol
    out = {}
    for code, e in pol.emp_table().items():
        if e.get("usable") and not pol.consistent(e):
            for key in ("avg_salary_derived", "salary_total"):
                v = e.get(key)
                if v == v and v is not None:
                    for iv in {int(round(v)), int(v)}:
                        if iv >= 1_000_000:
                            out[iv] = code
    return out


def scan(site_data: Path, held: dict[int, str], dirs: list[str] | None = None) -> list[tuple[str, str, int]]:
    hits = []
    roots = [site_data / d for d in dirs] if dirs else [site_data]
    for root in roots:
        for p in root.rglob("*.json"):
            for m in TOKEN.finditer(p.read_text(encoding="utf-8", errors="ignore")):
                v = int(m.group(0))
                if v in held:
                    hits.append((p.relative_to(site_data).as_posix(), held[v], v))
    return hits


def own_record_leaks(site_data: Path, held: dict[int, str]) -> list[tuple[str, str, int]]:
    """보류 기업 '자신의' 공개 레코드(법인 샤드·사람인 값 샤드)에 자기 보류값이 있는지. 다른 기업의 정상 값과 숫자가 우연히 같은 경우(중앙값·동일 총액 등)는 누출이 아니므로 구분한다."""
    by_code: dict[str, set[int]] = {}
    for v, c in held.items():
        by_code.setdefault(c, set()).add(v)
    leaks = []
    for sub in ("corp", "pay/s"):
        base = site_data / sub
        if not base.exists():
            continue
        for p in base.glob("*.json"):
            for code, rec in json.loads(p.read_text(encoding="utf-8")).items():
                toks = by_code.get(code)
                if toks:
                    for m in TOKEN.finditer(json.dumps(rec, ensure_ascii=False)):
                        if int(m.group(0)) in toks:
                            leaks.append((f"{sub}/{p.name}", code, int(m.group(0))))
    return leaks


def structural_corp_check(site_data: Path) -> list[str]:
    """법인 샤드: level != ok 인 dart 는 avg·total 이 null 이고 consistency 필드가 없어야 한다."""
    bad = []
    for p in (site_data / "corp").glob("*.json"):
        for code, r in json.loads(p.read_text(encoding="utf-8")).items():
            d = r.get("dart")
            if d and d.get("level") != "ok" and (d.get("avg") is not None or d.get("total") is not None or "consistency" in d):
                bad.append(code)
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="*")
    a = ap.parse_args()
    sd = ROOT / "site/data"
    held = held_values()
    print(f"보류 기업 값 {len(held):,}개 토큰으로 site/data 대조")
    bad = structural_corp_check(sd)
    own = own_record_leaks(sd, held)
    hits = scan(sd, held, a.dirs)
    print(f"구조 위반 {len(bad)}곳, 보류 기업 자기 레코드의 값 {len(own)}건, 다른 파일과 숫자 일치 {len(hits)}건(다른 기업의 정상 값과의 우연 일치 가능; 자기 레코드 누출만 실패 처리)")
    for h in own[:20]:
        print(" - 누출:", h)
    sys.exit(1 if bad or own else 0)
