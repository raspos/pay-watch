"""사업장 지표·비교집단·배지 (국민연금 자료만 사용). 계산할 수 없으면 NaN/None — 0 으로 채우지 않는다.
DART 가 필요한 지표(근속, 공시 급여, 재무 대비 보상)는 이 모듈에서 만들지 않는다(unavailable)."""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_BASE = 10          # 증감률 기준 시점 최소 가입자 수(작은 분모의 노이즈 방지)
TOP_N = 20             # 비교집단별로 내보내는 상위 목록 길이
MIN_PEER = 30          # 비교집단 최소 표본
CAP_NEAR = 0.9
SIZE_BINS = [9, 29, 99, 299, 999, 10**9]
SIZE_LABELS = ["10-29", "30-99", "100-299", "300-999", "1000+"]
UNCLASSIFIED = {"999999", "000000", ""}
# 건설 현장 단위 사업장(회사가 아니라 공사 현장별로 등록된 일용·상용 사업장). 예: "(주)ㅇㅇ/일용/ㅇㅇ현장 …"
PROJECT_SITE_RE = r"/(?:일용|상용)(?:직)?/|건설일용"


def is_project_site(name: pd.Series) -> pd.Series:
    return name.fillna("").str.contains(PROJECT_SITE_RE, regex=True)
RESTRUCTURE_MOM = 0.5  # 전월 대비 ±50% 이상(전월 30명 이상) 변동이 12개월 내 있으면 변동 확인 필요


def load_panel(interim_dir, months: list[str]) -> dict[str, pd.DataFrame]:
    """월별 interim parquet + ids parquet → wp_id × 월 와이드 표."""
    longs = []
    for ym in months:
        d = pd.read_parquet(f"{interim_dir}/nps_{ym}.parquet",
                            columns=["subscribers", "lost", "acquired", "est_monthly_income", "cap_ratio", "est_annual", "status"])
        ids = pd.read_parquet(f"{interim_dir}/ids_{ym}.parquet")[["wp_id"]]
        d = d.join(ids)
        d["ym"] = ym
        longs.append(d)
    L = pd.concat(longs, ignore_index=True)
    return {k: L.pivot(index="wp_id", columns="ym", values=v).reindex(columns=months)
            for k, v in {"subs": "subscribers", "lost": "lost", "acq": "acquired", "est_m": "est_monthly_income",
                         "cap": "cap_ratio"}.items()}


def size_bucket(n: pd.Series) -> pd.Series:
    return pd.cut(n, SIZE_BINS, labels=SIZE_LABELS)


def workplace_metrics(P: dict[str, pd.DataFrame], ms: list[str]) -> pd.DataFrame:
    """기준월 = ms[-1]. 12개월 지표는 13개월(ms[-13]..ms[-1])이 모두 있어야 계산한다."""
    S, LO, AC, E, C = (P[k][ms] for k in ("subs", "lost", "acq", "est_m", "cap"))
    t = ms[-1]
    out = pd.DataFrame(index=S.index)
    out["months_present"] = S.notna().sum(axis=1)
    out["subs"] = S[t]
    prev = S[ms[-2]] if len(ms) >= 2 else pd.Series(np.nan, index=S.index)
    out["subs_prev"] = prev
    out["mom_change"] = np.where(prev >= 1, S[t] / prev - 1, np.nan)
    out["lost_rate_month"] = np.where(prev >= MIN_BASE, LO[t] / prev, np.nan)       # 분모: 전월 가입자 수(고정 기준)
    out["acq_rate_month"] = np.where(prev >= MIN_BASE, AC[t] / prev, np.nan)

    have13 = len(ms) >= 13
    cols = {c: np.nan for c in ["growth_3m", "growth_12m", "net_12m", "persist_up_12m", "lost_cum_12m", "acq_cum_12m",
                                "pay_change_12m"]}
    out = out.assign(**cols)
    out["pay_change_reason"] = "insufficient_history"
    out["restructure_suspect"] = False
    if len(ms) >= 4:
        b3 = S[ms[-4]]
        out["growth_3m"] = np.where((b3 >= MIN_BASE) & S[t].notna(), S[t] / b3 - 1, np.nan)
    if have13:
        b12 = S[ms[-13]]
        ok = (b12 >= MIN_BASE) & S[t].notna()
        out["growth_12m"] = np.where(ok, S[t] / b12 - 1, np.nan)
        out["net_12m"] = np.where(S[t].notna() & b12.notna(), S[t] - b12, np.nan)
        win = S[ms[-13:]]
        full13 = win.notna().all(axis=1)
        out["persist_up_12m"] = np.where(full13, (win.diff(axis=1).iloc[:, 1:] > 0).sum(axis=1), np.nan)
        last12 = ms[-12:]
        full12 = S[last12].notna().all(axis=1)
        mean12 = S[last12].mean(axis=1)
        okc = full12 & (mean12 >= MIN_BASE)
        out["lost_cum_12m"] = np.where(okc, LO[last12].sum(axis=1) / mean12, np.nan)  # 실제 퇴사율 아님(납부예외 포함)
        out["acq_cum_12m"] = np.where(okc, AC[last12].sum(axis=1) / mean12, np.nan)
        mom = win.diff(axis=1).iloc[:, 1:] / win.shift(axis=1).iloc[:, 1:]
        base = win.shift(axis=1).iloc[:, 1:]
        out["restructure_suspect"] = ((mom.abs() > RESTRUCTURE_MOM) & (base >= 30)).any(axis=1)
        # 추정급여 변화율: 양쪽 달 모두 상한 접근이 아니고 가입자 10명 이상일 때만(상한 인상·절단 효과 배제)
        e_t, e_b, c_t, c_b = E[t], E[ms[-13]], C[t], C[ms[-13]]
        reason = pd.Series("ok", index=S.index)
        reason[e_t.isna() | e_b.isna()] = "missing"
        reason[(reason == "ok") & ((S[t] < MIN_BASE) | (b12 < MIN_BASE))] = "small_headcount"
        reason[(reason == "ok") & ((c_t >= CAP_NEAR) | (c_b >= CAP_NEAR))] = "cap_affected"
        out["pay_change_12m"] = np.where(reason == "ok", e_t / e_b - 1, np.nan)
        out["pay_change_reason"] = reason
    return out


def _group_label(x: pd.Series) -> str:
    x = x.dropna()
    if x.empty:
        return "업종명 없음"
    return x.mode().iat[0] + (f" 외 {x.nunique() - 1}개 업종" if x.nunique() > 1 else "")


def peer_table(df: pd.DataFrame) -> pd.DataFrame:
    """df: wp_id 인덱스, 컬럼 industry_code, industry_name, subs, est_annual, cap_flag, pay_public.
    비교집단은 '업종을 가장 세분한 것'부터 시도한다: 6자리 코드 → 4자리 → 2자리. 각 단계에서 같은 규모 구간(표본 30 이상)을 먼저,
    부족하면 인접 규모 구간 하나와 병합(…_merged). 끝까지 30곳 미만이면 NaN(규모 차이 큰 '업종 전체'로 대체하지 않음).
    NPS 업종코드는 자체 6자리 체계라 앞 2자리 묶음은 이질적일 수 있음(예: 74=엔지니어링·컨설팅·청소·변호사업)."""
    d = df.copy()
    code = d["industry_code"].fillna("")
    d["ind6"], d["ind4"], d["ind2"] = code, code.str[:4], code.str[:2]
    d["size_bucket"] = size_bucket(d["subs"])
    d["_b"] = d["size_bucket"].cat.codes.where(d["size_bucket"].notna(), -1)
    classified = ~code.isin(UNCLASSIFIED) & (d["ind2"] != "00")
    site = d["project_site"].fillna(False) if "project_site" in d else pd.Series(False, index=d.index)
    elig = d["pay_public"] & classified & d["est_annual"].notna() & (d["_b"] >= 0) & ~site   # 현장 단위 사업장은 비교집단에서 제외
    cols = ["peer_n", "peer_median", "peer_p25", "peer_p75"]
    for c in cols + ["pay_pct"]:
        d[c] = np.nan
    d["peer_scope"], d["peer_level"], d["peer_label"], d["peer_gkey"] = None, np.nan, None, None
    tops: dict = {}                                          # 비교집단별 상위 목록(상한 비접근만): "더 잘 주는 곳" 화면용

    def fill(rows_idx, members, keys, scope, level, wtag=None):
        g = members.groupby(keys, observed=True)
        st = g["est_annual"].agg(peer_n="size", peer_median="median", peer_p25=lambda x: x.quantile(.25), peer_p75=lambda x: x.quantile(.75))
        st["peer_label"] = g["industry_name"].agg(_group_label)
        st = st[st["peer_n"] >= MIN_PEER]
        sub = d.loc[rows_idx, keys].join(st, on=keys)
        ok = sub["peer_n"].notna()
        idx = ok[ok].index
        d.loc[idx, cols + ["peer_label"]] = sub.loc[idx, cols + ["peer_label"]]
        d.loc[idx, "peer_scope"] = scope
        d.loc[idx, "peer_level"] = level
        rk = members.groupby(keys, observed=True)["est_annual"].rank(pct=True, method="average")
        d.loc[idx, "pay_pct"] = rk.reindex(idx).values
        if len(idx):
            code = sub.loc[idx, keys[0]].astype(str)
            gk = f"{level}:" + code + (":b" + d.loc[idx, "_b"].astype(int).astype(str) if wtag is None else f":w{wtag}")
            d.loc[idx, "peer_gkey"] = gk
            used = set(gk.unique())
            for gv, gdf in members.groupby(keys, observed=True):
                c = gv[0] if isinstance(gv, tuple) else gv
                gkey = f"{level}:{c}:b{int(gv[1])}" if wtag is None else f"{level}:{c}:w{wtag}"
                if gkey not in used or gkey in tops:
                    continue
                capf = gdf["cap_flag"].fillna(False).astype(bool)
                ok = gdf[~capf].sort_values("est_annual", ascending=False).head(TOP_N)
                nm = ok["name_raw"] if "name_raw" in ok else pd.Series("", index=ok.index)
                tops[gkey] = {"n": int(len(gdf)), "capped": int(capf.sum()), "label": _group_label(gdf["industry_name"]), "scope": scope,
                              "size": SIZE_LABELS[int(gv[1])] if wtag is None else f"{SIZE_LABELS[wtag]} 및 {SIZE_LABELS[wtag + 1]}",
                              "items": [[int(i), str(nm[i]), int(round(ok.at[i, "est_annual"])), int(ok.at[i, "subs"]), ok.at[i, "industry_name"] if pd.notna(ok.at[i, "industry_name"]) else None] for i in ok.index]}
        return idx

    E = d[elig]
    todo = E.index
    last = len(SIZE_LABELS) - 1
    for level, key in ((6, "ind6"), (4, "ind4"), (2, "ind2")):
        got = fill(todo, E, [key, "_b"], f"code{level}_size", level)
        todo = todo.difference(got)
        for direction in ("right", "left"):                 # 인접 구간 병합: 먼저 큰 쪽, 안 되면 작은 쪽
            for lo in range(last):
                src = lo if direction == "right" else lo + 1
                rows = [i for i in todo if d.at[i, "_b"] == src]
                if not rows:
                    continue
                M = E[E["_b"].isin([lo, lo + 1])]
                got = fill(pd.Index(rows), M, [key], f"code{level}_merged", level, wtag=lo)
                todo = todo.difference(got)
    d["pay_premium"] = d["est_annual"] / d["peer_median"] - 1       # 비교집단 중앙값은 자기 포함(n≥30 이므로 영향 미미)
    d["pay_censored"] = d["cap_flag"].fillna(False) & d["pay_pct"].notna()   # 상한에 걸려 순위·프리미엄이 하한값
    out = d.drop(columns=["_b"])
    out.attrs["group_tops"] = tops
    return out


def badges(d: pd.DataFrame) -> pd.Series:
    """중립적 표현의 배지(단정적 평가 금지). 쉼표로 이어 붙인 코드 문자열."""
    out = pd.Series("", index=d.index)

    def add(mask, code):
        nonlocal out
        out = out.where(~mask.fillna(False), out + code + ",")

    rs = d["restructure_suspect"].fillna(False)
    add(d["cap_flag"].fillna(False), "cap_caution")                                      # 급여 상한 주의
    add((d["pay_pct"] >= 0.9) & ~d["pay_censored"].fillna(False), "pay_high_in_industry")   # 업종 내 고연봉
    add((d["growth_12m"] >= 0.10) & (d["subs"] >= 30) & ~rs, "headcount_up")                # 가입자 증가
    add((d["growth_12m"] <= -0.10) & (d["subs"] >= 30) & ~rs, "headcount_down")             # 가입자 감소
    add(d["lost_high"].fillna(False) & ~rs, "loss_rate_high")                               # 상실률 높음(퇴사율 아님)
    add(rs, "restructure_check")                                                            # 사업장 변동 확인 필요
    return out.str.rstrip(",")


def add_loss_peer_flag(d: pd.DataFrame) -> pd.DataFrame:
    """상실률 높음: 같은 업종×규모(표본 30 이상) 내 12개월 누적 상실률 상위 10%."""
    d = d.copy()
    d["lost_high"] = False
    ok = d["lost_cum_12m"].notna() & d["subs"].ge(MIN_BASE) & d["pay_public"].fillna(False)
    sub = d[ok & d["industry_code"].notna()].copy()
    sub["ind2"] = sub["industry_code"].str[:2]
    sub["size_bucket"] = size_bucket(sub["subs"])
    g = sub.groupby(["ind2", "size_bucket"], observed=True)["lost_cum_12m"]
    n, q = g.transform("size"), g.transform(lambda x: x.quantile(.9))
    hit = (n >= MIN_PEER) & (sub["lost_cum_12m"] >= q)
    d.loc[hit[hit].index, "lost_high"] = True
    return d
