import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from build_featured import resolve  # noqa: E402

ROWS = [
    [1, "삼성전자(주)", "업종", "수원", 126090, 1, 0],
    [2, "삼성전자서비스주식회사", "업종", "수원", 8101, 1, 0],       # 이름이 다름 → 선택되면 안 됨
    [3, "삼성전자 주식회사", "업종", "화성", 500, 1, 0],             # 같은 이름이지만 가입자가 적음
    [4, "에스케이하이닉스 주식회사", "업종", "이천", 37586, 1, 0],
    [5, "국민은행(주)", "업종", "서울", 14241, 1, 0],
]


def test_picks_exact_name_with_most_subscribers():
    out, missing = resolve([{"label": "삼성전자", "match": "삼성전자"}], ROWS)
    assert out == [{"label": "삼성전자", "id": 1, "name": "삼성전자(주)"}] and not missing


def test_english_initialism_alias_and_explicit_match_name():
    out, _ = resolve([{"label": "SK하이닉스", "match": "SK하이닉스"}, {"label": "KB국민은행", "match": "국민은행"}], ROWS)
    assert [o["id"] for o in out] == [4, 5]


def test_unresolved_items_are_skipped_not_faked():
    out, missing = resolve([{"label": "없는회사", "match": "없는회사"}, {"label": "삼성전자", "match": "삼성전자"}], ROWS)
    assert [o["label"] for o in out] == ["삼성전자"] and missing == ["없는회사"]


def test_config_never_labels_recommendations_as_popular():
    cfg = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "config/featured.yaml", encoding="utf-8"))
    assert "인기" not in cfg["heading"]
    assert all({"label", "match"} <= set(i) for i in cfg["items"])
