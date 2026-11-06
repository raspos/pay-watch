"""국민연금 가입 사업장 CSV 적재·정제. 실제 헤더/인코딩은 파일에서 확인한 값만 사용한다."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from .tables import CONFIG_DIR

NUMERIC = ["subscribers", "bill_amount", "acquired", "lost"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_encoding(path: Path) -> str:
    """utf-8(BOM 포함)로 엄격 디코딩이 되면 utf-8-sig, 아니면 cp949. 앞 4MB 로 판정."""
    raw = open(path, "rb").read(4 << 20)
    raw = raw[: raw.rfind(b"\n") + 1] or raw  # 문자 경계 보호
    try:
        raw.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError:
        raw.decode("cp949")  # 이것도 실패하면 예외 → 사람이 확인
        return "cp949"


def column_map() -> dict[str, str]:
    return yaml.safe_load(open(CONFIG_DIR / "data_sources.yaml", encoding="utf-8"))["nps"]["columns"]


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """헤더 접두어로 내부 이름에 매핑. 하나라도 빠지거나 남으면 실패(추측 금지)."""
    cmap, out, used = column_map(), {}, set()
    for col in df.columns:
        name = col.strip()
        # 긴 접두어부터 매칭 (예: '법정동주소광역시시군구읍면동코드' vs '법정동주소광역시시군구코드')
        for prefix in sorted(cmap, key=len, reverse=True):
            if name == prefix or name.startswith(prefix + " "):
                out[col] = cmap[prefix]
                used.add(prefix)
                break
        else:
            raise ValueError(f"알 수 없는 컬럼: {col!r}")
    missing = set(cmap) - used
    if missing:
        raise ValueError(f"필수 컬럼 누락: {sorted(missing)}")
    return df.rename(columns=out)


def read_nps_csv(path: Path) -> tuple[pd.DataFrame, dict]:
    path = Path(path)
    enc = detect_encoding(path)
    df = rename_columns(pd.read_csv(path, encoding=enc, dtype=str))
    months = sorted(df["ym"].dropna().unique())
    meta = {
        "file_name": path.name,
        "sha256": sha256_of(path),
        "size_bytes": path.stat().st_size,
        "encoding": enc,
        "rows": int(len(df)),
        "ym_values": months,
        "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return df, meta


_NAME_STRIP = re.compile(r"주식회사|\(주\)|㈜|\(유\)|유한회사|[\s\-_.,·]")


def normalize_name(s: str) -> str:
    """검색·비교용. 원본 사업장명은 별도 컬럼으로 반드시 보관한다."""
    # NFKC: 전각 괄호 （주）→(주), ㈜→(주), 전각 영문→반각을 먼저 통일(JS searchKey 와 동일 규칙)
    return _NAME_STRIP.sub("", unicodedata.normalize("NFKC", str(s))).upper()


_LETTER = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", ["에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠",
                                                  "엔", "오", "피", "큐", "알", "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트"]))


def normalize_alias(name_norm: str) -> str:
    """정규화명에서 영문 대문자 약자(2~5자)를 한글 음역으로 바꾼 보조 키. 예: GS글로벌→지에스글로벌.
    확정 근거가 아니라 후보 생성용이다(원본명·정규화명은 그대로 보존)."""
    return re.sub(r"[A-Z]{2,5}", lambda m: "".join(_LETTER[c] for c in m.group()), name_norm)


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(정제본, 격리본). 삭제하지 않고 사유를 남긴다."""
    df = df.copy()
    df["name_raw"] = df["name"]
    reasons = pd.Series("", index=df.index)

    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad_ym = ~df["ym"].fillna("").str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])")
    reasons[bad_ym] += "invalid_ym|"
    non_numeric = df[NUMERIC].isna().any(axis=1)
    reasons[non_numeric] += "non_numeric|"
    exact_dup = df.duplicated(keep="first")  # 모든 컬럼이 같은 행
    reasons[exact_dup] += "exact_duplicate|"

    quarantined = reasons != ""
    q = df[quarantined].assign(reason=reasons[quarantined].str.rstrip("|"))
    ok = df[~quarantined].copy()

    ok["name_norm"] = ok["name_raw"].map(normalize_name)
    for c in ("subscribers", "acquired", "lost"):
        ok[c] = ok[c].astype("int64")
    ok["bill_amount"] = ok["bill_amount"].astype("int64")
    ok["status"] = ok["status"].astype(str)
    ok["brn6"] = ok["brn6"].astype(str).str.zfill(6)
    ok["type_code"] = ok["type_code"].astype(str)
    # 같은 기준월에서 핵심 키가 같은 사업장: 합치지 않고 표시만 한다
    key = ["ym", "name_raw", "brn6", "applied_date", "sigungu", "emd", "addr_jibun"]
    ok["dup_key_flag"] = ok.duplicated(key, keep=False)
    ok = ok.sort_values(["ym", "name_raw", "brn6", "applied_date", "addr_jibun"]).reset_index(drop=True)
    return ok, q


def assert_no_month_overlap(existing: pd.DataFrame | None, new_months: list[str]) -> None:
    """동일 기준월 중복 입력 방지."""
    if existing is None or existing.empty:
        return
    dup = set(existing["ym"].unique()) & set(new_months)
    if dup:
        raise ValueError(f"이미 적재된 기준월입니다: {sorted(dup)}")
