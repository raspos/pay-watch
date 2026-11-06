// LAB 순수 로직(DOM 없음, node --test 로 검증). 값은 월임금총액(천원) 정수를 받아 연환산(×12)·만원 변환은 여기서 한다.
// 반올림은 표시(fmtMan)에서만 한다. 결측은 null 로 유지하며 0 으로 바꾸지 않는다.
export const KIND = {
  industry: { key: "industry", label: "산업", axis: "근속연수", binsKey: "industry", hint: "현 사업체 입사일부터 조사 기준일까지" },
  occupation: { key: "occupation", label: "직종", axis: "경력연수", binsKey: "occupation", hint: "공식 정의 미확인" },
};

// 월임금총액(천원) → 연환산(만원). 12개월 × 1,000원 ÷ 10,000원 = ×1.2. 정밀도 유지를 위해 반올림하지 않는다.
export const annualMan = m => (m == null ? null : (m * 12) / 10);
export const fmtMan = v => (v == null ? "비공개·자료 없음" : `${Math.round(v).toLocaleString("ko-KR")}만원`);
export const fmtN = n => (n == null ? "비공개·자료 없음" : `${Math.round(n).toLocaleString("ko-KR")}명`);
export const fmtPct = p => (p == null ? "-" : `${p >= 0 ? "+" : "−"}${Math.abs(p * 100).toFixed(1)}%`);

export const series = it => it.m.map(annualMan);                         // 구간별 연환산(만원), 결측 null
export const allAnnual = it => annualMan(it.mAll);

// 선택 구간 vs 같은 분류 전체 평균(전근속/전경력)
export function vsAll(it, bin) {
  const v = series(it)[bin], a = allAnnual(it);
  if (v == null || a == null) return { v, all: a, diff: null, pct: null };
  return { v, all: a, diff: v - a, pct: v / a - 1 };
}
// 같은 분류의 다른 구간과의 비교(선택 구간 대비)
export function binTable(it, bins, sel) {
  const s = series(it), base = s[sel];
  return bins.map((label, i) => ({ i, label, v: s[i], n: it.n[i], vsSel: s[i] == null || base == null || i === sel ? null : s[i] / base - 1, selected: i === sel }));
}
// 마지막 구간 ÷ 첫 구간(둘 다 있을 때만)
export const lastOverFirst = it => { const s = series(it); return s[0] != null && s[4] != null ? s[4] / s[0] : null; };

// 분류 검색: 이름·코드 부분 일치(대소문자 무시, 공백 무시). 전체 행(level==='전체')은 항상 앞에 둔다.
export function filterItems(items, q) {
  const k = String(q || "").replace(/\s+/g, "").toLowerCase();
  const hit = it => !k || (it.name + (it.code || "")).replace(/\s+/g, "").toLowerCase().includes(k);
  return items.filter(hit);
}
export const optionLabel = it => {
  const code = (it.code || "").replace(/^[A-Z]\((.*)\)$/, "$1");
  const sub = it.level === "중분류" || it.level === "소분류" ? "· " : "";
  const tag = it.level === "대분류" ? " [대분류]" : "";
  return `${sub}${it.name}${tag}${code ? ` (${code})` : ""}`;
};

// 그래프 좌표(순수). 가로 5구간 균등, 세로 0~nice max. 결측 구간은 점을 만들지 않고 선을 끊는다.
export function niceMax(v) {
  if (!(v > 0)) return 1000;
  const p = 10 ** Math.floor(Math.log10(v)), f = v / p;
  return ([1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find(c => f <= c + 1e-9) || 10) * p;
}
export function chartGeom(seriesList, { W = 640, H = 320, m = { l: 56, r: 16, t: 16, b: 44 } } = {}) {
  const vals = seriesList.flat().filter(v => v != null);
  const ymax = niceMax(Math.max(...vals, 0) * 1.05);
  const x = i => m.l + ((W - m.l - m.r) * (i + 0.5)) / 5, y = v => m.t + (H - m.t - m.b) * (1 - v / ymax);
  const out = seriesList.map(s => {
    const pts = s.map((v, i) => (v == null ? null : { i, v, x: x(i), y: y(v) }));
    const segs = []; let cur = [];
    for (const p of pts) { if (p) cur.push(p); else { if (cur.length) segs.push(cur); cur = []; } }
    if (cur.length) segs.push(cur);
    return { pts, segs };
  });
  const ticks = Array.from({ length: 5 }, (_, k) => (ymax * (k + 1)) / 5).map(v => ({ v, y: y(v) }));
  return { W, H, m, ymax, x, y, series: out, ticks };
}
