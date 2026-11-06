"""DART 수집 CLI(순차 실행·1건/초 이하). 사용:
  plan                      우선순위 대상과 예상 호출 수 계산(네트워크 없음)
  company [N]               기업개황: 계획의 1·3순위에서 아직 캐시 없는 것만 최대 N건
  emp YEAR [N]              직원현황(사업보고서): 매칭 점수≥3 법인만 최대 N건
  probe                     연결 1회 확인(10분에 1회)
  report                    수집 상태 리포트(reports/matching/dart_collection_status.md)"""
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paywatch.dart_client import (CACHE, LOGS, ROOT, STATE, Breaker, Dart, Halt, SingleRun, _read,  # noqa: E402
                                  usage_today)
from paywatch.load_nps import normalize_alias, normalize_name  # noqa: E402

PLAN = ROOT / "data/interim/dart_plan.parquet"
JUNK = r"유동화전문|제\d+차|투자회사|펀드|리츠|사모|투자조합|위탁관리|기업인수목적|스팩|SPAC"


def build_plan(min_unlisted_subs=300):
    cc = pd.read_parquet(ROOT / "data/interim/dart_corp_list.parquet")
    cc["nn"] = cc.corp_name.map(normalize_name)
    cc["na"] = cc.nn.map(normalize_alias)
    cc["listed"] = cc.stock_code != ""
    n = pd.read_parquet(ROOT / "data/interim/nps_2026-09.parquet", columns=["name_norm", "subscribers", "status"])
    n = n[(n.status == "1") & (n.subscribers >= 10)].copy()
    n["na"] = n.name_norm.map(normalize_alias)
    mx, mxa = n.groupby("name_norm").subscribers.max(), n.groupby("na").subscribers.max()
    cc["max_subs"] = cc.nn.map(mx).fillna(cc.na.map(mxa))
    cc["junk"] = cc.nn.str.contains(JUNK, regex=True)
    cc["dup_name"] = cc.groupby("nn").corp_code.transform("size") > 1
    cc["tier"] = 0
    # 1순위: 상장 + NPS 후보. 3순위: 비상장 + 가입자 큰 순 + 동명 중복 아님. (2순위는 emp 단계: 매칭 후 직원현황)
    cc.loc[cc.listed & cc.max_subs.notna(), "tier"] = 1
    cc.loc[~cc.listed & cc.max_subs.ge(min_unlisted_subs) & ~cc.junk & ~cc.dup_name, "tier"] = 3
    p = cc[cc.tier > 0].sort_values(["tier", "max_subs", "corp_code"], ascending=[True, False, True]).reset_index(drop=True)
    p["cached"] = [Dart.path("company", c).exists() for c in p.corp_code]
    p.to_parquet(PLAN)
    print(p.groupby("tier").agg(corps=("corp_code", "size"), cached=("cached", "sum")).assign(todo=lambda x: x.corps - x.cached))
    print("남은 기업개황 호출:", int((~p.cached).sum()), "/ 기존 계획(전체 후보) 41,619")


def run_company(d: Dart, budget):
    p = pd.read_parquet(PLAN)
    todo = [c for c in p.corp_code if not Dart.path("company", c).exists()][:budget]
    return loop(lambda c: d.get("company", c), todo)


def run_emp(d: Dart, year, budget):
    from paywatch.company_matcher import load_company_cache, match
    dart = load_company_cache()
    est = pd.read_parquet(ROOT / "data/interim/nps_2026-09.parquet").join(pd.read_parquet(ROOT / "data/interim/ids_2026-09.parquet")[["wp_id"]])
    res = match(est[(est.status == "1") & (est.subscribers >= 10)], dart)
    corps = res[res.score >= 3].merge(est[["wp_id", "subscribers"]], on="wp_id").groupby("corp_code").subscribers.sum().sort_values(ascending=False)
    todo = [c for c in corps.index if not Dart.path("empSttus", c, year, "11011").exists()][:budget]
    print("직원현황 대상(매칭 점수≥3 법인):", len(corps), "미수집", len(todo))
    return loop(lambda c: d.get("empSttus", c, year, "11011"), todo)


def loop(fn, todo):
    ok = err = 0
    for i, c in enumerate(todo):
        try:
            fn(c)
            ok += 1
        except Halt as e:
            print("중단:", e)
            break
        except Exception as e:
            err += 1
            print("ERR", c, str(e)[:100])
        if i % 100 == 0:
            print("progress", i, "/", len(todo), flush=True)
    print("완료", ok, "오류", err)


def report():
    rows = [json.loads(l) for l in open(LOGS / "dart_requests.jsonl", encoding="utf-8")] if (LOGS / "dart_requests.jsonl").exists() else []
    usage = _read(STATE / "usage.json", {})
    L = ["# DART 수집 상태", "", f"- 브레이커: {Breaker.state()}", f"- 오늘 호출: {usage_today()}", "", "## 일자별 호출량", "",
         "| 일자 | 호출 | 성공 | 데이터없음 | HTTP오류 | 연결오류 | DART오류 |", "|---|---|---|---|---|---|---|"]
    for k, v in sorted(usage.items()):
        L.append(f"| {k} | {v['calls']} | {v['ok']} | {v['no_data']} | {v['http_error']} | {v['conn_error']} | {v['dart_error']} |")
    c = Counter((r.get("api"), r.get("dart_status") or r.get("error") or r.get("http")) for r in rows)
    L += ["", "## 요청 로그 집계 (api, 결과)", ""] + [f"- {k}: {v}" for k, v in c.most_common()]
    L += ["", "## 캐시", ""] + [f"- {a.name}: {len(list(a.glob('*.json')))}건" for a in sorted(CACHE.iterdir()) if a.is_dir()]
    (ROOT / "reports/matching/dart_collection_status.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


def main():
    cmd = sys.argv[1]
    if cmd == "plan":
        return build_plan()
    if cmd == "report":
        return report()
    with SingleRun():
        d = Dart()
        if cmd == "probe":
            print(d.probe())
        elif cmd == "company":
            run_company(d, int(sys.argv[2]) if len(sys.argv) > 2 else 10**9)
        elif cmd == "emp":
            run_emp(d, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10**9)
        print("이번 실행 API 호출 수:", d.calls)


if __name__ == "__main__":
    try:
        main()
    except Halt as e:
        print("중단:", e)
