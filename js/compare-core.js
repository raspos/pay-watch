// 월급 배틀 판정 로직(순수 함수, DOM 없음). 원칙: 같은 종류·같은 기준의 값끼리만 우열을 표시하고, 종합 점수·단일 승자는 만들지 않는다.
export const MAX_ITEMS = 4;
export const MIN_ITEMS = 2;
export const CAP_NEAR = 0.9;
export const SCOPE_MIN = 0.7, SCOPE_MAX = 1.3;

const last = a => (a && a.length ? a[a.length - 1] : null);
const num = v => (v === undefined || v === null || Number.isNaN(v) ? null : v);

// ---- 입력 정규화 ----
export function fromCorp(c) {
  const s = c.nps.series;
  let payChange = null;                                   // 상한 접근이 아닌 시작·끝 달 모두 있을 때만(상한 인상 효과 배제)
  const e0 = num(s.est[0]), e1 = num(last(s.est)), c0 = num(s.cap[0]), c1 = num(last(s.cap));
  if (e0 && e1 && c0 != null && c1 != null && c0 < CAP_NEAR && c1 < CAP_NEAR) payChange = e1 / e0 - 1;
  const d = c.dart;
  return {
    key: `c${c.code}`, kind: "corp", name: c.n.replace(/\(주\)|주식회사|㈜/g, "").trim(), loc: c.loc, href: `company.html?corp=${c.code}`,
    hold: !!c.hold, saramin: c.saramin && c.saramin.v != null ? { avg: c.saramin.v, fy: c.saramin.y } : null,
    dart: d ? { avg: d.level === "ok" ? d.avg : null, level: d.level, tenure: num(d.tenure), fy: d.fy, topPct: d.pos ? d.pos.top_pct : null, peerN: d.pos ? d.pos.n : null } : null,
    est: num(c.nps.est), cap: num(c.nps.cap), subs: num(c.nps.subs), g12: num(c.nps.g12), payChange, scope: num(c.scope),
  };
}

// 상세 자료가 없는 기업·사람인 전용 기업(검색 색인에만 있음): 가진 값만 담고 나머지는 없음. extra: {dart, saramin}
export function fromEntity(e, extra = {}) {
  const dart = extra.dart || null, sm = extra.saramin || null, isDart = /^\d{8}$/.test(e.code);
  return { key: isDart ? `c${e.code}` : `s${String(e.code).slice(1)}`, kind: "corp", name: String(e.display || e.legal).replace(/\(주\)|주식회사|㈜/g, "").trim(), loc: "",
    href: isDart ? `company.html?corp=${e.code}` : `company.html?sm=${e.code}`, hold: false, noData: !dart && !sm,
    dart: dart ? { avg: dart.avg, level: "ok", tenure: num(dart.tenure), fy: dart.fy, topPct: null, peerN: null } : null,
    saramin: sm && sm.v != null ? { avg: sm.v, fy: sm.y } : null, est: null, cap: null, subs: null, g12: null, payChange: null, scope: null };
}

export function fromWorkplace(d) {
  return {
    key: `w${d.id}`, kind: "wp", name: d.n, loc: d.loc, href: `company.html?id=${d.id}&view=wp`, dart: null,
    est: d.pp && d.e ? num(last(d.e)) : null, cap: d.pp && d.c ? num(last(d.c)) : null, subs: num(last(d.s)), g12: num(d.m.g12),
    payChange: d.pp ? num(d.m.pc12) : null, scope: null,
  };
}

// ---- URL 토큰: items=c00126380,w228151 (회사=c+고유번호, 사업장=w+id). 예전 a=,b= 링크(사업장 id)도 받는다 ----
export function parseItems(search) {
  const q = new URLSearchParams(search);
  let toks = (q.get("items") || "").split(",").map(s => s.trim()).filter(Boolean);
  if (!toks.length) toks = ["a", "b"].map(k => q.get(k)).filter(Boolean).map(v => `w${v}`);
  const seen = new Set();
  return toks.filter(t => /^(?:[cw]\d+|s[0-9a-f]{10})$/.test(t) && !seen.has(t) && seen.add(t)).slice(0, MAX_ITEMS);
}
export const toQuery = keys => (keys.length ? `?items=${keys.join(",")}` : "");

// ---- 비교 항목 정의 ----
export const ROWS = [
  { id: "dart_avg", primary: true, title: "공시 1인 평균급여", tag: "공시 기준 계산값", basis: "DART 사업보고서 직원현황의 급여총액을 직원 수로 나눈 값. 일관성 검증을 통과한 회사만 비교합니다.",
    get: e => (e.dart && e.dart.level === "ok" ? e.dart.avg : null), fmt: "man", missingHint: "공시 급여가 없거나 일관성 검증을 통과하지 못한 회사" },
  { id: "saramin_avg", primary: true, title: "사람인 추정 평균연봉", tag: "추정(사람인)", basis: "사람인 통계 추정값(표시연도). DART 공시값과 출처·산정 방식이 달라 서로 섞어 우열을 가리지 않습니다.",
    get: e => (e.saramin ? e.saramin.avg : null), fmt: "man", missingHint: "사람인 추정 평균연봉이 없는 회사" },
  { id: "nps_est", title: "국민연금 기반 연환산 추정금액", tag: "추정", basis: "국민연금 기준소득월액을 연환산한 추정값(상한 적용). 상한에 접근한 회사가 하나라도 있으면 우열을 가리지 않습니다.",
    get: e => e.est, fmt: "man", needNoCap: true },
  { id: "pay_change", title: "12개월 추정급여 변화", tag: "추정", basis: "시작·끝 달 모두 상한에 접근하지 않은 경우만 계산합니다. 직원 구성 변화가 섞여 있어 임금 인상률이 아닙니다.",
    get: e => e.payChange, fmt: "pct", signed: true, missingHint: "상한에 접근했거나 12개월 자료가 부족해 계산하지 않은 회사" },
  { id: "subs", title: "국민연금 가입자 수", tag: "원자료", basis: "확인된 사업장의 국민연금 가입자 합계입니다. 회사 전체 직원 수가 아닙니다.", get: e => e.subs, fmt: "int", needScope: true },
  { id: "g12", title: "12개월 가입자 증감", tag: "계산", basis: "두 시점 모두 있는 사업장 기준의 국민연금 가입자 증감률입니다. 사업장 이동·통합의 영향을 받을 수 있습니다.",
    get: e => e.g12, fmt: "pct", signed: true },
  { id: "tenure", primary: true, title: "평균 근속연수", tag: "공시 기준 계산값", basis: "DART 직원현황의 근속연수를 직원 수로 가중평균한 값입니다.", get: e => (e.dart ? e.dart.tenure : null), fmt: "year" },
  { id: "pos", title: "동종업계 내 위치(공시 기준)", tag: "공시 기준 계산값", basis: "회사마다 비교집단(업종·규모)이 달라 순위를 직접 비교하지 않고 각자의 위치만 보여줍니다.",
    get: e => (e.dart ? e.dart.topPct : null), fmt: "top", noBars: true },
];

// ---- 한 항목의 비교 판정 ----
export function evaluateRow(row, ents) {
  const values = ents.map(row.get);
  const present = values.map((v, i) => (v === null ? -1 : i)).filter(i => i >= 0);
  const out = { id: row.id, values, present, comparable: false, reason: null, leaders: [], max: null, maxAbs: null, signed: !!row.signed, capped: [] };
  if (row.noBars) { out.reason = "비교집단이 서로 달라 순위를 직접 비교하지 않습니다."; return out; }
  if (present.length < 2) {
    const miss = ents.filter((_, i) => values[i] === null).map(e => e.name).join(", ");
    const why = row.missingHint && miss ? ` ${row.missingHint}: ${miss}.` : "";
    out.reason = (present.length ? "비교할 수 있는 값이 한 곳뿐이라 우열을 가리지 않습니다." : "비교할 수 있는 값이 없습니다.") + why;
    return out;
  }
  const pv = present.map(i => values[i]);
  out.max = Math.max(...pv);
  out.maxAbs = Math.max(...pv.map(Math.abs));
  if (row.needNoCap) {
    out.capped = present.filter(i => ents[i].cap !== null && ents[i].cap >= CAP_NEAR);
    if (out.capped.length) { out.reason = `상한 접근(${out.capped.map(i => ents[i].name).join(", ")}): 추정값이 하한값이라 우열을 가리지 않습니다.`; return out; }
  }
  if (row.needScope) {
    const off = present.filter(i => ents[i].kind === "corp" && ents[i].scope !== null && (ents[i].scope < SCOPE_MIN || ents[i].scope > SCOPE_MAX));
    if (off.length) { out.reason = `확인된 사업장 기준이라 회사 전체 규모 비교가 아닙니다(${off.map(i => ents[i].name).join(", ")}). 우열을 가리지 않습니다.`; return out; }
  }
  out.comparable = true;
  out.leaders = present.filter(i => values[i] === out.max);        // 동률이면 모두 강조
  if (out.leaders.length === present.length) out.leaders = [];     // 전부 같으면 강조할 대상이 없다
  return out;
}

export function evaluateAll(ents) {
  const rows = ROWS.map(r => ({ row: r, res: evaluateRow(r, ents) }));
  return { rows, comparableRows: rows.filter(x => x.res.comparable).length };
}

export function fmtValue(row, v) {
  if (v === null) return "자료 없음";
  if (row.fmt === "man") return `${Math.round(v / 10000).toLocaleString("ko-KR")}만원`;
  if (row.fmt === "int") return `${Math.round(v).toLocaleString("ko-KR")}명`;
  if (row.fmt === "pct") return `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  if (row.fmt === "year") return `${v.toFixed(1)}년`;
  if (row.fmt === "top") return `상위 ${v}%`;
  return String(v);
}
