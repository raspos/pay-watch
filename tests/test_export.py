import json

import numpy as np
import pandas as pd

from paywatch.export_public import (DETAIL_KEYS, METRIC_KEYS, N_SHARDS, build_detail, chunk_name, index_row, search_key,
                                    shard_of)

MS = [f"2025-{m:02d}" for m in range(9, 13)] + [f"2026-{m:02d}" for m in range(1, 10)]


def make_row(pay_public=True, **kw):
    base = dict(name_raw="(주)테스트", type_code="1", industry_name="업종", ind2="47", addr_jibun="서울특별시 중구 태평로2가",
                pay_public=pay_public, growth_12m=0.1, growth_3m=np.nan, net_12m=10, mom_change=0.0, lost_rate_month=0.01,
                lost_cum_12m=0.2, acq_cum_12m=0.3, persist_up_12m=5, restructure_suspect=False, history_complete=True,
                pay_change_12m=np.nan, pay_change_reason="cap_affected", project_site=False, pay_pct=0.5, pay_premium=0.1, pay_censored=False,
                peer_n=40, peer_median=3e7, peer_p25=2.5e7, peer_p75=3.5e7, peer_scope="industry_size", size_bucket="30-99",
                badges="cap_caution", grade="C", flags="cap_near|below_public_threshold", subs=50, brn6="123456", zip="12345",
                addr_road="상세도로명", est_annual=3.2e7, cap_flag=False)
    base.update(kw)
    return pd.Series(base, name=777)


def rows(est=3_000_000.0, subs=50.0):
    return {"subs": np.array([subs] * 13), "acq": np.array([1.0] * 13), "lost": np.array([2.0] * 13),
            "est": np.array([est] * 13), "cap": np.array([0.5] * 13)}


def test_detail_uses_allowlist_and_hides_identifiers():
    dt = build_detail(make_row(), rows(), MS)
    assert set(dt) <= DETAIL_KEYS and set(dt["m"]) <= METRIC_KEYS
    blob = json.dumps(dt, ensure_ascii=False)
    for secret in ("123456", "12345", "상세도로명", "brn6"):
        assert secret not in blob


def test_unavailable_stays_null_not_zero():
    dt = build_detail(make_row(), rows(), MS)
    assert dt["m"]["g3"] is None and dt["m"]["pc12"] is None


def test_non_public_workplace_has_no_pay_fields():
    dt = build_detail(make_row(pay_public=False, grade="D"), rows(subs=5.0), MS)
    assert dt["pp"] is False and dt["e"] is None and dt["c"] is None and dt["peer"] is None and dt["grade"] is None
    assert "pct" not in dt["m"] and "prem" not in dt["m"]
    assert "below_public_threshold" not in dt["fl"]


def test_estimate_months_below_ten_subscribers_are_blank():
    r = rows()
    r["subs"][0] = 7.0
    dt = build_detail(make_row(), r, MS)
    assert dt["e"][0] is None and dt["e"][1] == 36_000_000


def test_missing_months_are_null():
    r = rows()
    r["subs"][3] = np.nan
    r["est"][3] = np.nan
    dt = build_detail(make_row(), r, MS)
    assert dt["s"][3] is None and dt["e"][3] is None


def test_shard_deterministic_and_bounded():
    assert shard_of(5) == shard_of(5 + N_SHARDS) and 0 <= shard_of(10**9 + 7) < N_SHARDS


def test_search_key_matches_alias_rules():
    assert search_key("SK하이닉스(주)") == "에스케이하이닉스"
    assert search_key("에스케이하이닉스 주식회사") == "에스케이하이닉스"
    assert chunk_name("삼성전자") == f"{ord('삼'):x}_{ord('성'):x}"


def test_index_row_has_no_secrets():
    r = index_row(make_row())
    assert len(r) == 7 and "123456" not in json.dumps(r, ensure_ascii=False)


def test_nan_strings_never_reach_json():
    # 업종명·소재지가 비어 있어도 유효한 JSON(NaN 금지)으로 직렬화되어야 한다
    r = make_row(industry_name=np.nan, addr_jibun=np.nan, badges=np.nan, flags=np.nan, peer_label=np.nan, pay_change_reason=np.nan)
    dt = build_detail(r, rows(), MS)
    s = json.dumps(dt, ensure_ascii=False, allow_nan=False)
    assert json.loads(s)["ind"] is None and json.loads(s)["loc"] is None
    json.dumps(index_row(r), ensure_ascii=False, allow_nan=False)


def test_dict_records_are_supported():
    r = make_row().to_dict()
    r["_id"] = 42
    assert build_detail(r, rows(), MS)["id"] == 42 and index_row(r)[0] == 42


# ---- 정렬 키 범위 청크 ----
from paywatch.export_public import chunks_for_prefix, range_partition  # noqa: E402


def _recs(keys):
    return [(k, [i, k]) for i, k in enumerate(keys)]


def test_range_partition_keeps_equal_keys_together_and_sorted():
    keys = ["가", "가", "가", "나", "다", "다", "라", "마", "마", "마"]
    chunks, starts = range_partition(_recs(keys), size=3)
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    for c, s in zip(chunks, starts):
        assert c[0][0] == s
    # 같은 키는 두 청크에 걸치지 않음
    where = {}
    for n, c in enumerate(chunks):
        for k, _ in c:
            assert where.setdefault(k, n) == n


def test_prefix_lookup_finds_every_match_like_bruteforce():
    import random
    random.seed(7)
    alpha = list("가나다라마바사아자차")
    keys = ["".join(random.choice(alpha) for _ in range(random.randint(1, 4))) for _ in range(3000)]
    chunks, starts = range_partition(_recs(keys), size=40)
    for q in ["가", "나다", "마바사", "아자차가", "라라", "하"]:
        got = {k for n in chunks_for_prefix(starts, q, cap=10**9) for k, _ in chunks[n] if k.startswith(q)}
        assert got == {k for k in keys if k.startswith(q)}, q


def test_prefix_lookup_cap_limits_files():
    keys = ["가" + str(i % 50) for i in range(2000)]
    chunks, starts = range_partition(_recs(keys), size=10)
    assert len(chunks_for_prefix(starts, "가", cap=6)) <= 6


def test_scrub_turns_nan_and_numpy_into_valid_json():
    from paywatch.export_public import scrub
    o = {"a": float("nan"), "b": [np.float64(1.5), np.int64(3), float("inf")], "c": {"d": pd.NA, "e": "x"}}
    s = json.dumps(scrub(o), allow_nan=False)
    assert json.loads(s) == {"a": None, "b": [1.5, 3, None], "c": {"d": None, "e": "x"}}
