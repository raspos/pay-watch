import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from build_dist import HI, LO, histogram  # noqa: E402
from paywatch.corp_layer import PEER_MIN, aggregate_corp, dart_peers, peer_hist  # noqa: E402
from paywatch.tables import load_caps  # noqa: E402

MS = [f"2025-{m:02d}" for m in range(9, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]


def panel(subs, est):
    mk = lambda rows: pd.DataFrame(rows, index=[10, 20, 30][:len(rows)], columns=MS, dtype=float)
    z = [[0] * 13] * len(subs)
    return {"subs": mk(subs), "est_m": mk(est), "acq": mk(z), "lost": mk(z), "cap": mk([[0.5] * 13] * len(subs))}


def test_aggregate_weights_by_subscribers_and_skips_small_workplaces():
    P = panel([[100] * 13, [300] * 13, [5] * 13], [[3_000_000] * 13, [5_000_000] * 13, [9_000_000] * 13])
    a = aggregate_corp("X", [10, 20, 30], P, MS, pd.DataFrame(), load_caps())
    assert a["subs"].iloc[-1] == 405                                   # 가입자 합계는 5명짜리도 포함
    # 급여 추정: 10명 이상 사업장만, 가입자 가중평균 (100*3.0M + 300*5.0M)/400 = 4.5M
    assert a["est_annual"].iloc[-1] == pytest.approx(4_500_000 * 12)
    assert a["primary"] == 20


def test_aggregate_growth_uses_same_workplaces_only():
    # 두 번째 사업장은 12개월 전에 없었음 → 증감률은 두 시점 모두 있는 첫 사업장만으로 계산(신규 사업장 효과 배제)
    s = [[100] * 12 + [110], [np.nan] * 12 + [500]]
    s[0] = [100.0] + [100.0] * 11 + [110.0]
    P = panel(s, [[3e6] * 13, [3e6] * 13])
    a = aggregate_corp("X", [10, 20], P, MS, pd.DataFrame(), load_caps())
    assert a["g12"] == pytest.approx(0.10) and a["net12"] == 10
    # 기준 가입자가 50명 미만이면 증감률을 내지 않는다
    P2 = panel([[20.0] * 12 + [30.0]], [[3e6] * 13])
    assert aggregate_corp("Y", [10], P2, MS, pd.DataFrame(), load_caps())["g12"] is None


def emp_rows(n, ind="264", employees=500):
    return pd.DataFrame({"corp_code": [f"{i:08d}" for i in range(n)], "usable": True, "consistency": 0.01, "employees": employees,
                         "avg_salary_derived": [50_000_000 + i * 1_000_000 for i in range(n)]})


def comp(n, ind="264"):
    return pd.DataFrame({"corp_code": [f"{i:08d}" for i in range(n)], "induty_code": ind, "corp_name": [f"회사{i}" for i in range(n)]})


def test_dart_peers_need_min_sample():
    assert dart_peers(emp_rows(PEER_MIN - 1), comp(PEER_MIN - 1)).empty
    p = dart_peers(emp_rows(PEER_MIN), comp(PEER_MIN))
    assert len(p) == PEER_MIN and (p["peer_n"] == PEER_MIN).all()


def test_dart_peers_exclude_inconsistent_and_top_pct():
    e = emp_rows(40)
    e.loc[0, "consistency"] = 0.30                                      # 일관성 불통과 법인은 비교집단에서 제외
    p = dart_peers(e, comp(40))
    assert "00000000" not in p.index and (p["peer_n"] == 39).all()
    best = p.loc["00000039"]
    assert best["top_pct"] == 1 and best["hist"]["counts"] and sum(best["hist"]["counts"]) == 39


def test_peer_hist_counts_sum_to_n():
    v = pd.Series(np.random.default_rng(1).normal(80_000_000, 20_000_000, 200))
    h = peer_hist(v)
    assert sum(h["counts"]) == 200 and len(h["counts"]) == 20 and h["step"] > 0


def test_dist_histogram_counts_everything_once():
    est = pd.Series([5e6, LO, LO + 1, 4e7, HI - 1, HI, 9e7])
    edges, counts = histogram(est)
    assert sum(counts) == len(est) and counts[0] == 1 and counts[-1] == 2 and len(counts) == len(edges) + 1


def test_dart_peer_groups_have_ids_sorted_top_list_and_exclude_inconsistent():
    e = emp_rows(40)
    e.loc[39, "consistency"] = 0.30                                    # 가장 높은 급여지만 일관성 불통과 → 목록에 없어야 함
    p = dart_peers(e, comp(40))
    groups = p.attrs["groups"]
    assert len(groups) == 1 and set(p["gid"]) == {0}
    g = groups["0"]
    assert g["n"] == 39 and len(g["items"]) == 30
    avgs = [it[2] for it in g["items"]]
    assert avgs == sorted(avgs, reverse=True) and g["items"][0][0] == "00000038"
    assert all(it[0] != "00000039" for it in g["items"]) and g["items"][0][1] == "회사38"


def test_dart_group_ids_are_deterministic():
    a = dart_peers(emp_rows(40), comp(40))
    b = dart_peers(emp_rows(40), comp(40))
    assert a.attrs["groups"].keys() == b.attrs["groups"].keys() and (a["gid"] == b["gid"]).all()
