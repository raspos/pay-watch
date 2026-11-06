"""OpenDART 클라이언트 v2.
- 단일 실행 잠금(동시에 수집 프로세스 1개), 프로세스 간 공유되는 전역 호출 간격(기본 1초/건)
- 디스크 캐시(중복 수집 방지·이어받기), 요청 로그(jsonl), 일일 호출량 기록
- 지수 백오프(제한 횟수), 서킷 브레이커(연속 연결 실패·명시적 거부/제한 응답 시 중단 상태 유지)
키는 로그·캐시·예외 메시지에 남기지 않는다."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DART_DIR = ROOT / "data/raw/dart"
CACHE = DART_DIR / "cache"
STATE = DART_DIR / "state"
LOGS = DART_DIR / "logs"
BASE = "https://opendart.fss.or.kr/api/"

# 사용자 제보: 분당 1,000건 초과 시 1시간 차단(공식 문서 미확인). 1건/초 = 분당 60건으로 충분히 낮게 유지
MIN_INTERVAL = 1.0            # 초/건. 공식 문서에 초당 허용치가 없어 보수적으로 1건/초 이하로 시작
DAILY_SOFT_CAP = 10_000       # 문서상 '일반적으로 20,000건 이상'에서 020 → 절반만 사용
CONN_FAIL_TRIP = 3            # 연속 연결 실패 N회면 브레이커 오픈
CONN_COOLDOWN_MIN = 30
BACKOFF = (2, 4, 8)
RETRY_DART = {"800", "900"}
# 서버가 명시적으로 거부/제한을 알린 상태: 존중하고 즉시 중단
REFUSE_DART = {"010", "011", "012", "020", "901"}
REFUSE_HTTP = {401, 403, 429}


class Halt(RuntimeError):
    """수집을 계속하면 안 되는 상태(브레이커 오픈·일일 상한·명시적 거부)."""


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes  # Windows: os.kill 은 프로세스를 종료시킬 수 있으므로 사용하지 않는다
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259  # STILL_ACTIVE


class SingleRun:
    """동시에 하나의 수집 프로세스만 허용."""

    def __init__(self):
        self.path = STATE / "fetch.lock"

    def __enter__(self):
        STATE.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            pid = _read(self.path, {}).get("pid")
            if pid and _pid_alive(pid) and pid != os.getpid():
                raise Halt(f"이미 수집 프로세스가 실행 중입니다(pid {pid})")
        _write(self.path, {"pid": os.getpid(), "started": datetime.now().isoformat(timespec="seconds")})
        return self

    def __exit__(self, *a):
        try:
            self.path.unlink()
        except OSError:
            pass


class Breaker:
    path = STATE / "breaker.json"

    @classmethod
    def state(cls) -> dict:
        return _read(cls.path, {"open": False, "consecutive_conn_fail": 0})

    @classmethod
    def check(cls):
        s = cls.state()
        if s.get("open"):
            until = s.get("until")
            if until and datetime.fromisoformat(until) <= datetime.now() and s.get("kind") == "conn":
                # 연결 실패 쿨다운이 끝나면 '반개방': 호출자가 probe 로 1회만 확인하도록 닫지 않고 안내
                raise Halt(f"브레이커 반개방: 쿨다운 종료({until}). `fetch_dart.py probe` 로 1회 확인 후 해제하세요")
            raise Halt(f"브레이커 오픈({s.get('kind')}: {s.get('reason')}), 재개 가능 시각 {until}")

    @classmethod
    def trip(cls, kind: str, reason: str, minutes: int | None = None, until_tomorrow: bool = False):
        until = None
        if until_tomorrow:
            until = (datetime.combine(date.today(), datetime.min.time()) + timedelta(days=1, hours=1)).isoformat(timespec="seconds")
        elif minutes:
            until = (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        _write(cls.path, {"open": True, "kind": kind, "reason": reason, "until": until,
                          "tripped_at": datetime.now().isoformat(timespec="seconds"), "consecutive_conn_fail": cls.state().get("consecutive_conn_fail", 0)})

    @classmethod
    def note_conn(cls, ok: bool):
        s = cls.state()
        s["consecutive_conn_fail"] = 0 if ok else s.get("consecutive_conn_fail", 0) + 1
        _write(cls.path, s)
        if not ok and s["consecutive_conn_fail"] >= CONN_FAIL_TRIP:
            cls.trip("conn", f"연속 연결 실패 {s['consecutive_conn_fail']}회", minutes=CONN_COOLDOWN_MIN)

    @classmethod
    def reset(cls):
        _write(cls.path, {"open": False, "consecutive_conn_fail": 0, "reset_at": datetime.now().isoformat(timespec="seconds")})


def usage_today() -> dict:
    u = _read(STATE / "usage.json", {})
    return u.setdefault(date.today().isoformat(), {"calls": 0, "ok": 0, "no_data": 0, "http_error": 0, "conn_error": 0, "dart_error": 0})


def _bump(field: str):
    u = _read(STATE / "usage.json", {})
    d = u.setdefault(date.today().isoformat(), {"calls": 0, "ok": 0, "no_data": 0, "http_error": 0, "conn_error": 0, "dart_error": 0})
    d[field] = d.get(field, 0) + 1
    _write(STATE / "usage.json", u)


def _log(**kw):
    LOGS.mkdir(parents=True, exist_ok=True)
    kw["ts"] = datetime.now().isoformat(timespec="seconds")
    with open(LOGS / "dart_requests.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(kw, ensure_ascii=False) + "\n")


class Dart:
    def __init__(self, interval: float = MIN_INTERVAL):
        load_dotenv(ROOT / ".env")
        self.key = os.environ.get("DART_API_KEY", "")
        if len(self.key) != 40:
            raise RuntimeError("DART_API_KEY 가 .env 에 없거나 40자가 아닙니다")
        self.interval = max(interval, MIN_INTERVAL)  # 더 빠르게는 설정할 수 없음
        self.s = requests.Session()
        self.calls = 0

    @staticmethod
    def path(api: str, corp: str, year: str = "", rc: str = "") -> Path:
        return CACHE / api / f"{corp}_{year}_{rc}.json"

    def _throttle(self):
        last = _read(STATE / "last_call.json", {}).get("t", 0)  # 프로세스 간 공유
        wait = last + self.interval - time.time()
        if wait > 0:
            time.sleep(wait)
        _write(STATE / "last_call.json", {"t": time.time()})

    def get(self, api: str, corp: str, year: str = "", rc: str = "") -> dict:
        p = self.path(api, corp, year, rc)
        if p.exists():  # 캐시 적중: 호출·카운트 없음
            return json.loads(p.read_text(encoding="utf-8"))
        Breaker.check()
        if usage_today()["calls"] >= DAILY_SOFT_CAP:
            raise Halt(f"일일 호출 상한({DAILY_SOFT_CAP}) 도달")
        params = {"crtfc_key": self.key, "corp_code": corp}
        if year:
            params.update(bsns_year=year, reprt_code=rc)
        for attempt in range(len(BACKOFF) + 1):
            self._throttle()
            t0 = time.time()
            self.calls += 1
            _bump("calls")
            try:
                r = self.s.get(f"{BASE}{api}.json", params=params, timeout=30)
            except requests.RequestException as e:
                _bump("conn_error")
                _log(api=api, corp=corp, year=year, stage="connect/http", error=type(e).__name__, ms=int((time.time() - t0) * 1000))
                Breaker.note_conn(False)
                Breaker.check()
                if attempt < len(BACKOFF):
                    time.sleep(BACKOFF[attempt])
                    continue
                raise Halt(f"연결 실패({type(e).__name__}) {api} {corp}")
            Breaker.note_conn(True)
            if r.status_code in REFUSE_HTTP:
                _bump("http_error")
                _log(api=api, corp=corp, http=r.status_code, note="명시적 거부/제한: 중단")
                Breaker.trip("refused", f"HTTP {r.status_code}", until_tomorrow=True)
                raise Halt(f"HTTP {r.status_code}: 서버가 접근을 거부/제한함")
            if r.status_code >= 500:
                _bump("http_error")
                _log(api=api, corp=corp, http=r.status_code)
                if attempt < len(BACKOFF):
                    time.sleep(BACKOFF[attempt])
                    continue
                raise Halt(f"HTTP {r.status_code} 반복")
            try:
                j = r.json()
            except ValueError:
                _bump("http_error")
                _log(api=api, corp=corp, http=r.status_code, note="JSON 아님")
                raise RuntimeError(f"JSON 이 아닌 응답 ({api} {corp})")
            st = j.get("status")
            _log(api=api, corp=corp, year=year, http=r.status_code, dart_status=st, msg=j.get("message"), ms=int((time.time() - t0) * 1000))
            if st in REFUSE_DART:
                _bump("dart_error")
                Breaker.trip("refused", f"DART {st} {j.get('message')}", until_tomorrow=True)
                raise Halt(f"DART {st}: {j.get('message')}")
            if st in RETRY_DART and attempt < len(BACKOFF):
                time.sleep(BACKOFF[attempt])
                continue
            if st == "000":
                _bump("ok")
            elif st == "013":
                _bump("no_data")
            else:
                _bump("dart_error")
                raise RuntimeError(f"DART status {st} {j.get('message')} ({api} {corp})")
            _write(p, j)
            return j
        raise Halt("재시도 소진")

    def probe(self) -> dict:
        """연결 확인 1회(삼성전자 기업개황, 캐시 무시). 10분에 1회만 허용."""
        pr = _read(STATE / "probe.json", {})
        if pr.get("t") and time.time() - pr["t"] < 600:
            raise Halt("probe 는 10분에 1회만 허용됩니다")
        _write(STATE / "probe.json", {"t": time.time()})
        self._throttle()
        t0 = time.time()
        try:
            r = self.s.get(f"{BASE}company.json", params={"crtfc_key": self.key, "corp_code": "00126380"}, timeout=20)
            out = {"ok": True, "http": r.status_code, "dart_status": r.json().get("status"), "ms": int((time.time() - t0) * 1000)}
            Breaker.reset() if out["dart_status"] == "000" else None
        except requests.RequestException as e:
            out = {"ok": False, "error": type(e).__name__, "ms": int((time.time() - t0) * 1000)}
        _log(api="company", corp="probe", **{k: v for k, v in out.items() if k != "ok"})
        return out
