"""DART 파서·매칭·클라이언트 안전장치 테스트. 합성 데이터만 사용하며 네트워크를 호출하지 않는다."""
import json

import pandas as pd
import pytest

import paywatch.dart_client as dc
from paywatch.company_matcher import addr_key, match, parse_emp
from paywatch.load_nps import normalize_alias, normalize_name


def emp_rows(rows):
    base = dict(rcept_no="X", corp_cls="Y", corp_code="00000001", corp_name="가상", stlm_dt="2025-12-31", rm="-")
    return {"status": "000", "list": [{**base, **r} for r in rows]}


def r(fo, sex, sm, tot="-", ten="1.0"):
    return dict(fo_bbm=fo, sexdstn=sex, sm=sm, fyer_salary_totamt=tot, avrg_cnwk_sdytrn=ten, jan_salary_am="-")


# ---- 직원현황 파서 ----
def test_parse_emp_weighted_average_from_gender_totals():
    j = emp_rows([r("DX", "남", "10"), r("DS", "여", "5"),                      # 사업부문 행: 급여 없음 → 합산 금지
                  r("성별합계", "남", "1,000", "100,000,000,000", "10.0"), r("성별합계", "여", "500", "30,000,000,000", "4.0")])
    e = parse_emp(j)
    assert e["usable"] and e["employees"] == 1500
    assert e["avg_salary_derived"] == pytest.approx(130_000_000_000 / 1500)       # 단순 평균(두 성별 평균의 평균)이 아님
    assert e["avg_tenure_weighted"] == pytest.approx((10 * 1000 + 4 * 500) / 1500)


def test_parse_emp_segment_rows_not_summed():
    j = emp_rows([r("A사업부", "남", "100"), r("B사업부", "남", "200")])
    e = parse_emp(j)
    assert not e["usable"] and e["reason"] == "missing_salary_or_headcount"


def test_parse_emp_missing_salary_is_unusable_not_zero():
    e = parse_emp(emp_rows([r("성별합계", "남", "100", "-"), r("성별합계", "여", "50", "-")]))
    assert not e["usable"] and "avg_salary_derived" not in e


def test_parse_emp_no_data_status():
    assert parse_emp({"status": "013", "message": "조회된 데이타가 없습니다."}) is None


# ---- 이름 정규화·음역 ----
def test_alias_normalization():
    assert normalize_alias(normalize_name("(주)GS글로벌")) == "지에스글로벌"
    assert normalize_alias(normalize_name("아시아나IDT(주)")) == "아시아나아이디티"
    assert normalize_alias("네이버") == "네이버"
    assert normalize_name("주식회사 카카오") == "카카오"


def test_addr_key():
    assert addr_key("경기도 수원시 영통구  삼성로 129 (매탄동)") == ("경기", "수원시")
    assert addr_key("서울특별시 서초구 양재동") == ("서울", "서초구")
    assert addr_key(None) is None


# ---- 매칭 ----
def dart_df(rows):
    return pd.DataFrame([{**dict(stock_code="", corp_cls="E", jurir_no="", induty_code="", acc_mt="12"), **x} for x in rows])


def nps_df(rows):
    return pd.DataFrame(rows)


def test_match_grades():
    dart = dart_df([dict(corp_code="C1", corp_name="(주)가나다", bizr_no="1234567890", adres="서울특별시 강남구 1"),
                    dict(corp_code="C2", corp_name="(주)라마바", bizr_no="2223334444", adres="부산광역시 중구 1"),
                    dict(corp_code="C3", corp_name="LG테스트", bizr_no="3334445555", adres="서울특별시 중구 2")])
    nps = nps_df([
        dict(wp_id=1, name_norm="가나다", brn6="123456", addr_jibun="서울특별시 강남구 역삼동"),       # high
        dict(wp_id=2, name_norm="가나다", brn6="123456", addr_jibun="경기도 성남시 분당구"),           # candidate(주소 불일치)
        dict(wp_id=3, name_norm="라마바", brn6="999999", addr_jibun="대구광역시 중구"),                 # 이름만(번호6 불일치)
        dict(wp_id=4, name_norm="엘지테스트", brn6="333444", addr_jibun="서울특별시 중구 3"),           # 음역 + 번호6 + 시군구
        dict(wp_id=5, name_norm="없는회사", brn6="111111", addr_jibun="서울특별시 중구 3"),             # 근거 없음
        dict(wp_id=6, name_norm="엘지테스트", brn6="333444", addr_jibun="부산광역시 해운대구"),         # 음역 + 번호6, 주소 불일치
    ])
    g = match(nps, dart).set_index("wp_id")
    assert g.loc[1, "grade"] == "high_confidence" and g.loc[1, "corp_code"] == "C1"
    assert g.loc[2, "grade"] == "candidate" and g.loc[2, "score"] == 4
    assert g.loc[3, "grade"] == "candidate" and g.loc[3, "score"] == 2
    assert g.loc[4, "grade"] == "high_confidence" and g.loc[4, "evidence"] == "alias_name+brn6+sigungu"
    assert g.loc[6, "grade"] == "candidate" and g.loc[6, "score"] == 3
    assert g.loc[5, "grade"] == "unmatched"
    assert "verified" not in set(g["grade"])  # 자동으로 verified 가 되지 않음


def test_match_ambiguous_when_two_corps_tie():
    dart = dart_df([dict(corp_code="C1", corp_name="동명", bizr_no="1234560001", adres="서울특별시 강남구 1"),
                    dict(corp_code="C2", corp_name="동명", bizr_no="1234560002", adres="서울특별시 강남구 2")])
    g = match(nps_df([dict(wp_id=1, name_norm="동명", brn6="123456", addr_jibun="서울특별시 강남구 3")]), dart)
    assert g.loc[0, "grade"] == "ambiguous" and pd.isna(g.loc[0, "corp_code"])


# ---- 클라이언트 안전장치 ----
@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(dc, "STATE", tmp_path / "state")
    monkeypatch.setattr(dc, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(dc.Breaker, "path", tmp_path / "state/breaker.json")
    monkeypatch.setenv("DART_API_KEY", "k" * 40)
    monkeypatch.setattr(dc, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    return tmp_path


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {"status": "000"}

    def json(self):
        return self._b


def test_interval_floor_cannot_be_lowered(sandbox):
    assert dc.Dart(interval=0.01).interval == dc.MIN_INTERVAL


def test_cache_hit_makes_no_call(sandbox):
    d = dc.Dart()
    p = d.path("company", "00000001")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"status": "000", "corp_name": "x"}), encoding="utf-8")
    d.s.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("네트워크 호출 금지"))
    assert d.get("company", "00000001")["corp_name"] == "x" and d.calls == 0


def test_breaker_trips_on_repeated_connection_failures(sandbox):
    import requests
    d = dc.Dart()
    d.s.get = lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("x"))
    with pytest.raises(dc.Halt):
        d.get("company", "00000001")
    assert dc.Breaker.state()["open"] and d.calls <= dc.CONN_FAIL_TRIP  # 무한 재시도 없음
    with pytest.raises(dc.Halt):
        d.get("company", "00000002")
    assert d.calls <= dc.CONN_FAIL_TRIP  # 오픈 후에는 호출하지 않음


def test_rate_limit_020_respected(sandbox):
    d = dc.Dart()
    d.s.get = lambda *a, **k: FakeResp(200, {"status": "020", "message": "limit"})
    with pytest.raises(dc.Halt):
        d.get("company", "00000001")
    n = d.calls
    with pytest.raises(dc.Halt):
        d.get("company", "00000002")
    assert d.calls == n and dc.Breaker.state()["kind"] == "refused"


def test_http_403_stops(sandbox):
    d = dc.Dart()
    d.s.get = lambda *a, **k: FakeResp(403)
    with pytest.raises(dc.Halt):
        d.get("company", "00000001")
    assert d.calls == 1


def test_no_data_is_cached_and_counted(sandbox):
    d = dc.Dart()
    d.s.get = lambda *a, **k: FakeResp(200, {"status": "013", "message": "no"})
    d.get("empSttus", "00000001", "2025", "11011")
    d.get("empSttus", "00000001", "2025", "11011")
    assert d.calls == 1 and dc.usage_today()["no_data"] == 1


def test_log_never_contains_key(sandbox):
    d = dc.Dart()
    d.s.get = lambda *a, **k: FakeResp()
    d.get("company", "00000001")
    assert ("k" * 40) not in (sandbox / "logs/dart_requests.jsonl").read_text(encoding="utf-8")


def test_single_run_lock(sandbox):
    with dc.SingleRun():
        with pytest.raises(dc.Halt):
            # 다른 프로세스가 잡고 있다고 가정: 살아있는 다른 pid(부모)를 기록
            import os
            dc._write(dc.STATE / "fetch.lock", {"pid": os.getppid() or 1})
            dc.SingleRun().__enter__()


def test_fullwidth_parentheses_normalized():
    # 전각 괄호·㈜·전각 영문이 반각과 같은 키로 정규화되어야 검색 접두어·DART 이름 매칭이 맞는다
    assert normalize_name("（주）에스케이켐텍") == normalize_name("(주)에스케이켐텍") == "에스케이켐텍"
    assert normalize_name("㈜카카오") == "카카오"
    assert normalize_name("주식회사칼라천국（ＣＯＬＯＲ）") == normalize_name("주식회사칼라천국(COLOR)")


# ---- 실제 응답 형태(캐시에서 확인된 패턴) ----
def test_parse_emp_all_rows_carry_salary_summed_when_no_total_row():
    # 경농 형태: (제조업, 남)/(제조업, 여) 두 행에 각각 급여가 있고 합계 행은 없다
    j = emp_rows([r("제조업", "남", "314", "20,297,274,000", "9.2"), r("제조업", "여", "71", "3,563,963,000", "8.4")])
    e = parse_emp(j)
    assert e["usable"] and e["basis"] == "모든 행" and e["employees"] == 385
    assert e["avg_salary_derived"] == pytest.approx((20_297_274_000 + 3_563_963_000) / 385)


def test_parse_emp_total_rows_preferred_over_segments_no_double_count():
    j = emp_rows([r("생산직", "남", "100", "10,000,000,000"), r("사무직", "남", "50", "6,000,000,000"),
                  r("전사", "남", "150", "16,000,000,000"), r("전사", "여", "50", "4,000,000,000")])
    e = parse_emp(j)
    assert e["basis"] == "전사" and e["employees"] == 200 and e["salary_total"] == 20_000_000_000


def test_parse_emp_inconsistency_recorded_not_hidden():
    rows = [r("전체", "남", "100", "10,000,000,000"), r("전체", "여", "100", "10,000,000,000")]
    for x in rows:
        x["jan_salary_am"] = "150,000,000"          # 보고된 1인 평균이 총액÷인원(1억)과 크게 다름
    e = parse_emp(emp_rows(rows))
    assert e["usable"] and e["consistency"] > 0.3


def test_parse_emp_consistent_small_gap():
    rows = [r("전체", "남", "100", "10,000,000,000"), r("전체", "여", "100", "10,000,000,000")]
    for x in rows:
        x["jan_salary_am"] = "100,000,000"
    assert parse_emp(emp_rows(rows))["consistency"] == pytest.approx(0.0)


def test_manual_override_marks_verified_by_brn6_and_name():
    dart = dart_df([dict(corp_code="N1", corp_name="NAVER", bizr_no="2208162517", adres="경기도 성남시 분당구 1")])
    nps = nps_df([dict(wp_id=7, name_norm="네이버", brn6="220816", addr_jibun="경기도 성남시 분당구 정자동"),
                  dict(wp_id=8, name_norm="네이버", brn6="999999", addr_jibun="서울특별시 중구")])
    ov = pd.DataFrame([dict(brn6="220816", name_norm="네이버", corp_code="N1", evidence="사업자번호6·주소 일치 확인")])
    g = match(nps, dart, ov).set_index("wp_id")
    assert g.loc[7, "grade"] == "verified" and g.loc[7, "corp_code"] == "N1"
    assert g.loc[8, "grade"] == "unmatched"            # 같은 이름이어도 사업자번호6 이 다르면 확정되지 않음


def test_unit_error_values_are_not_usable_and_not_corrected():
    # 천원 단위로 공시된 경우(평균 7만, 4.6e10 등): 임의로 ×1000 보정하지 않고 계산 불가 + 사유 기록
    low = parse_emp(emp_rows([r("전체", "남", "20", "1,500,000"), r("전체", "여", "14", "1,000,000")]))
    assert not low["usable"] and low["reason"] == "implausible_value_unit_suspect" and low["avg_salary_raw"] < 1e5
    high = parse_emp(emp_rows([r("전체", "남", "100", "9,000,000,000,000"), r("전체", "여", "100", "1,000,000,000,000")]))
    assert not high["usable"] and high["reason"] == "implausible_value_unit_suspect"
    ok = parse_emp(emp_rows([r("전체", "남", "20", "1,500,000,000"), r("전체", "여", "14", "1,000,000,000")]))
    assert ok["usable"]
