import pandas as pd

from paywatch.workplace_ids import assign_month


def wp(name, brn="111111", applied="2000-01-01", dong="1100000000", sg="110", **kw):
    return dict(name_norm=name, brn6=brn, applied_date=applied, legal_dong=dong, sigungu=sg, **kw)


def run(prev_rows, cur_rows):
    prev, nid = assign_month(pd.DataFrame(prev_rows), None, 1)
    cur, _ = assign_month(pd.DataFrame(cur_rows), prev, nid)
    return prev, cur


def test_row_order_does_not_change_id():
    prev, cur = run([wp("A"), wp("B", brn="222222")], [wp("B", brn="222222"), wp("A")])
    assert cur.loc[0, "wp_id"] == prev.loc[1, "wp_id"] and cur.loc[1, "wp_id"] == prev.loc[0, "wp_id"]


def test_name_change_keeps_id():
    prev, cur = run([wp("OLD")], [wp("NEW")])
    assert cur.loc[0, "wp_id"] == prev.loc[0, "wp_id"] and cur.loc[0, "link_tier"] == "t2_brn_applied_sigungu"


def test_ambiguous_not_linked():
    # 같은 사업자번호6·적용일자·시군구에 이름이 다른 후보가 둘 → 연결하지 않고 새 ID
    prev, cur = run([wp("A"), wp("B")], [wp("C", dong="9"), wp("D", dong="8")])
    assert set(cur["wp_id"]).isdisjoint(set(prev["wp_id"])) and (cur["link_tier"] == "new").all()


def test_same_name_different_brn_not_merged():
    prev, cur = run([wp("A", brn="111111")], [wp("A", brn="222222")])
    assert cur.loc[0, "link_tier"] == "new"


def test_ids_unique_within_month():
    _, cur = run([wp("A"), wp("B", brn="2")], [wp("A"), wp("B", brn="2"), wp("C", brn="3")])
    assert cur["wp_id"].is_unique
