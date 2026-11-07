import { CONTACT, VIEWS_URL } from "./site-config.js";
import { showViews } from "./views.js";
// 공통: 정규화(파이썬 export_public.search_key 와 동일 규칙), 데이터 로더, 서식, SVG 차트
const BASE = new URL("../data/", import.meta.url);
const cache = new Map();

export async function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(new URL(path, BASE)).then(r => {
      if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path);
}
export const getMeta = () => getJSON("meta.json");
export async function getDetail(id, nShards = 1024) {
  const sh = await getJSON(`d/${Number(id) % nShards}.json`);
  return sh[String(id)] || null;
}

// ---- 검색 키: 주식회사/(주) 등 제거 → 대문자 → 영문 약자(2~5자)를 한글 음역으로 ----
const LET = { A:"에이",B:"비",C:"씨",D:"디",E:"이",F:"에프",G:"지",H:"에이치",I:"아이",J:"제이",K:"케이",L:"엘",M:"엠",
  N:"엔",O:"오",P:"피",Q:"큐",R:"알",S:"에스",T:"티",U:"유",V:"브이",W:"더블유",X:"엑스",Y:"와이",Z:"제트" };
export function searchKey(s) {
  const n = String(s).normalize("NFKC").replace(/주식회사|\(주\)|㈜|\(유\)|유한회사|[\s\-_.,·]/g, "").toUpperCase();
  return n.replace(/[A-Z]{2,5}/g, m => [...m].map(c => LET[c]).join(""));
}
export const chunkName = sk => [...sk].slice(0, 2).map(c => c.codePointAt(0).toString(16)).join("_");

// ---- 서식 ----
export const fmtInt = n => n == null ? "—" : Math.round(n).toLocaleString("ko-KR");
export const fmtMan = n => n == null ? "—" : `${Math.round(n / 10000).toLocaleString("ko-KR")}만원`;
export const fmtPct = (x, d = 1, sign = true) => x == null ? "—" : `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;
export const ymShort = ym => `${ym.slice(2, 4)}.${ym.slice(5)}`;
export const last = a => a[a.length - 1];
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));

export const FLAG_KO = {
  cap_near: "국민연금 상한에 접근(추정이 실제보다 낮을 수 있음)", above_cap_anomaly: "상한을 넘는 이상값", very_low_estimate: "추정값이 비정상적으로 낮음",
  withdrawn: "탈퇴 사업장", zero_bill: "고지금액 0", no_subscribers: "가입자 없음", dup_key: "같은 달 동일 키 사업장 중복",
  no_rate_for_month: "해당 월 보험료율 없음", no_cap_for_month: "해당 월 상한액 없음", negative_bill: "음수 고지금액" };
export const BADGE_KO = { cap_caution: "급여 상한 주의", pay_high_in_industry: "업종 내 고연봉", headcount_up: "가입자 증가",
  headcount_down: "가입자 감소", loss_rate_high: "상실률 높음", restructure_check: "사업장 변동 확인 필요" };
export const GRADE_INFO = {
  B: "국민연금 추정치가 있고 큰 이상 신호가 없음(확정 연봉이 아님)",
  C: "상한 접근·이상값 등으로 해석에 주의가 필요함",
  D: "데이터 부족 또는 이상으로 비교에 부적합" };
export const PCR_KO = { cap_affected: "상한 영향으로 계산하지 않음", small_headcount: "가입자 10명 미만 시점이 있어 계산하지 않음",
  missing: "12개월 전 자료 없음", insufficient_history: "12개월 자료 부족" };

// ---- SVG 라인 차트 (null 은 선을 끊고 0 으로 그리지 않음) ----
export function lineChart(el, { labels, series, yFmt = fmtInt, title, desc, height = 220, yMin = null }) {
  const W = 640, H = height, m = { l: 56, r: 12, t: 12, b: 28 };
  const vals = series.flatMap(s => s.values).filter(v => v != null);
  const id = "c" + Math.random().toString(36).slice(2, 8);
  if (!vals.length) { el.innerHTML = `<div class="empty-state">표시할 자료가 없습니다</div>`; return; }
  let lo = yMin ?? Math.min(...vals), hi = Math.max(...vals);
  if (hi === lo) { hi += Math.abs(hi) * .05 || 1; lo -= Math.abs(lo) * .05 || 1; }
  const pad = (hi - lo) * .12; if (yMin == null) lo -= pad; hi += pad;
  const x = i => m.l + (W - m.l - m.r) * (labels.length === 1 ? .5 : i / (labels.length - 1));
  const y = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
  const ticks = [0, .25, .5, .75, 1].map(f => lo + (hi - lo) * f);
  let g = ticks.map(t => `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text class="axis" x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${esc(yFmt(t))}</text>`).join("");
  g += labels.map((l, i) => (i % 2 === 0 || i === labels.length - 1) ? `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>` : "").join("");
  const colors = ["var(--s1)", "var(--s2)"];
  series.forEach((s, k) => {
    let d = "", pen = false;
    s.values.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
    const col = colors[k % 2];
    if (k === 0) {                                   // 첫 계열 아래 연한 영역(연속 구간별, 결측 구간은 비움)
      let seg = [];
      const flush = () => { if (seg.length > 1) g += `<path class="area" fill="${col}" d="M${seg[0][0].toFixed(1)},${H - m.b}${seg.map(p => `L${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("")}L${seg[seg.length - 1][0].toFixed(1)},${H - m.b}Z"/>`; seg = []; };
      s.values.forEach((v, i) => { if (v == null) flush(); else seg.push([x(i), y(v)]); });
      flush();
    }
    g += `<path d="${d}" fill="none" stroke="${col}" stroke-width="2.5" ${s.dash ? 'stroke-dasharray="6 4"' : ""} stroke-linejoin="round"/>`;
    g += s.values.map((v, i) => v == null ? "" : `<circle cx="${x(i)}" cy="${y(v)}" r="3.5" fill="${col}"><title>${esc(s.name)} ${esc(labels[i])}: ${esc(yFmt(v))}</title></circle>`).join("");
  });
  const rows = labels.map((l, i) => `<tr><th scope="row">${esc(l)}</th>${series.map(s => `<td class="num">${s.values[i] == null ? "—" : esc(yFmt(s.values[i]))}</td>`).join("")}</tr>`).join("");
  el.innerHTML = `<figure class="chart" role="group" aria-labelledby="${id}t" aria-describedby="${id}d">
    <figcaption id="${id}t"><b>${esc(title)}</b></figcaption>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}">${g}</svg>
    <div class="legend">${series.map((s, k) => `<span><i style="background:${colors[k % 2]}"></i>${esc(s.name)}</span>`).join("")}</div>
    <p class="disclaimer" id="${id}d">${esc(desc || "")}</p>
    <details class="data"><summary>데이터 표로 보기</summary><div class="tablewrap"><table><thead><tr><th>월</th>${series.map(s => `<th class="num">${esc(s.name)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div></details></figure>`;
}

export function barChart(el, { labels, series, title, desc, height = 220 }) {
  // 막대 2계열(취득/상실). null 은 빈 칸.
  const W = 640, H = height, m = { l: 56, r: 12, t: 12, b: 28 };
  const vals = series.flatMap(s => s.values).filter(v => v != null);
  const id = "b" + Math.random().toString(36).slice(2, 8);
  if (!vals.length) { el.innerHTML = `<div class="empty-state">표시할 자료가 없습니다</div>`; return; }
  const hi = Math.max(...vals, 1) * 1.1;
  const y = v => m.t + (H - m.t - m.b) * (1 - v / hi);
  const bw = (W - m.l - m.r) / labels.length, colors = ["var(--s1)", "var(--s2)"];
  let g = [0, .5, 1].map(f => `<line class="gridline" x1="${m.l}" x2="${W - m.r}" y1="${y(hi * f)}" y2="${y(hi * f)}"/><text class="axis" x="${m.l - 6}" y="${y(hi * f) + 4}" text-anchor="end">${esc(fmtInt(hi * f))}</text>`).join("");
  labels.forEach((l, i) => {
    if (i % 2 === 0 || i === labels.length - 1) g += `<text class="axis" x="${m.l + bw * (i + .5)}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>`;
    series.forEach((s, k) => { const v = s.values[i]; if (v == null) return;
      const w = bw * .36, xx = m.l + bw * i + bw * .12 + k * (w + 2);
      g += `<rect x="${xx}" y="${y(v)}" width="${w}" height="${H - m.b - y(v)}" fill="${colors[k]}" rx="2"><title>${esc(s.name)} ${esc(l)}: ${esc(fmtInt(v))}</title></rect>`; });
  });
  const rows = labels.map((l, i) => `<tr><th scope="row">${esc(l)}</th>${series.map(s => `<td class="num">${s.values[i] == null ? "—" : fmtInt(s.values[i])}</td>`).join("")}</tr>`).join("");
  el.innerHTML = `<figure class="chart" role="group" aria-labelledby="${id}t"><figcaption id="${id}t"><b>${esc(title)}</b></figcaption>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}">${g}</svg>
    <div class="legend">${series.map((s, k) => `<span><i style="background:${colors[k]}"></i>${esc(s.name)}</span>`).join("")}</div>
    <p class="disclaimer">${esc(desc || "")}</p>
    <details class="data"><summary>데이터 표로 보기</summary><div class="tablewrap"><table><thead><tr><th>월</th>${series.map(s => `<th class="num">${esc(s.name)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div></details></figure>`;
}

// 기준소득월액 상한의 연환산 값(설정값 meta.caps 기준, 거꾸로 계산한 근사치를 쓰지 않는다)
export function capAnnual(meta, ym) {
  const c = (meta.caps || []).find(x => x.from <= ym && ym <= x.to);
  return c ? c.upper * 12 : null;
}

// ---- 그래픽 헬퍼 (장식용은 aria-hidden, 의미 있는 것은 텍스트 대체 제공) ----
const I = p => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
export const ICON = {
  coin: I('<circle cx="12" cy="12" r="9"/><path d="M12 6.5v11M9.2 9.3h4.2a1.9 1.9 0 0 1 0 3.8h-2.8a1.9 1.9 0 0 0 0 3.8h4.4"/>'),
  gem: I('<path d="M6 3h12l4 6-10 12L2 9z"/><path d="M2 9h20M9 3l3 6 3-6M12 21 9 9m3 12 3-12"/>'),
  up: I('<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>'),
  users: I('<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><path d="M17 5v6M14 8h6"/>'),
  vs: I('<path d="M4 5l4 14 4-14M20 6c-1.5-1-5-1-5 1.5s5 2 5 5S16.500 19 15 18"/>'),
  alert: I('<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17.200v.1"/>'),
};
export function sparkline(values, { color = "var(--g1)" } = {}) {
  const v = values.map(x => (x == null ? null : x)), nn = v.filter(x => x != null);
  if (nn.length < 2) return "";
  const W = 120, H = 34, lo = Math.min(...nn), hi = Math.max(...nn), r = hi - lo || 1;
  const x = i => 2 + (W - 4) * i / (v.length - 1), y = a => H - 4 - (H - 8) * (a - lo) / r;
  let d = "", pen = false;
  v.forEach((a, i) => { if (a == null) { pen = false; return; } d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(a).toFixed(1)}`; pen = true; });
  const li = v.length - 1 - [...v].reverse().findIndex(a => a != null);
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/><circle cx="${x(li)}" cy="${y(v[li])}" r="3" fill="${color}"/></svg>`;
}
export function gauge(ratio) {
  // 반원 게이지: 0 ~ 1.1(상한의 110%). 0.9 지점에 눈금. 색: 0.7 미만 파랑, 0.9 미만 주황, 그 이상 빨강
  const f = Math.max(0, Math.min(ratio / 1.1, 1)), cx = 100, cy = 100, R = 80;
  const pt = (t, r = R) => [cx + r * Math.cos(Math.PI * (1 - t)), cy - r * Math.sin(Math.PI * (1 - t))];
  const [ex, ey] = pt(f), [t1x, t1y] = pt(.9 / 1.1, R - 12), [t2x, t2y] = pt(.9 / 1.1, R + 10);
  const col = ratio >= .9 ? "var(--danger)" : ratio >= .7 ? "#e09400" : "var(--s1)";
  return `<svg viewBox="0 0 200 112" role="img" aria-label="상한 접근도 ${ratio.toFixed(3)} (0.9 이상이면 주의)">
    <path d="M20,100 A80,80 0 0 1 180,100" fill="none" stroke="var(--grid)" stroke-width="16" stroke-linecap="round"/>
    <path d="M20,100 A80,80 0 ${f > .5 ? 1 : 0} 1 ${ex.toFixed(1)},${ey.toFixed(1)}" fill="none" stroke="${col}" stroke-width="16" stroke-linecap="round"/>
    <line x1="${t1x.toFixed(1)}" y1="${t1y.toFixed(1)}" x2="${t2x.toFixed(1)}" y2="${t2y.toFixed(1)}" stroke="var(--ink)" stroke-width="2"/>
    <text x="100" y="92" text-anchor="middle" font-size="26" font-weight="800" fill="var(--ink)">${ratio.toFixed(2)}</text>
    <text x="100" y="108" text-anchor="middle" class="axis">상한 대비</text></svg>`;
}
export function avatar(name) {
  const base = String(name).replace(/주식회사|\(주\)|㈜|\(유\)|유한회사|[\s\-_.,·]/g, "") || "?";
  let h = 0; for (const c of base) h = (h * 31 + c.codePointAt(0)) % 360;
  return `<div class="avatar" aria-hidden="true" style="background:hsl(${h} 55% 40%)">${esc([...base][0].toUpperCase())}</div>`;
}

export function chrome(active) {
  const nav = [["index.html", "홈"], ["rank.html", "친구들 랭킹"], ["compare.html", "월급 배틀"], ["lab.html", "LAB"], ["methodology.html", "방법론"]];
  document.body.insertAdjacentHTML("afterbegin", `<a class="skip" href="#main">본문으로 건너뛰기</a>
  <header class="site"><div class="wrap"><a class="brand" href="index.html" aria-label="PAY워치, 내 친구는 얼마벌까? 홈">PAY워치</a>
  <nav class="main" aria-label="주요 메뉴">${nav.map(([h, t]) => `<a href="${h}" ${h === active ? 'aria-current="page"' : ""}>${t}</a>`).join("")}</nav></div></header>`);
  document.body.insertAdjacentHTML("beforeend", `<footer class="site"><div class="wrap">
  <p>회사 단위 통계이며 개인의 실제 연봉이 아닙니다. 공시 평균급여(DART 사업보고서)와 국민연금 고지액 기반 추정급여는 서로 다른 지표입니다. <a href="methodology.html">방법론·출처·한계</a>${CONTACT ? ` · <a href="${esc(CONTACT.href)}">${esc(CONTACT.label)}</a>` : ""}</p>
  <p class="copy">© <a href="https://raspos.github.io/databrew/" target="_blank" rel="noopener">databrew</a> <span id="visits" hidden></span></p></div></footer>`);
  if (VIEWS_URL) { let st = null; try { st = sessionStorage; } catch { /* 사생활 보호 모드 */ } showViews({ url: VIEWS_URL, el: document.getElementById("visits"), storage: st }); }
}


// ---- 분포 히스토그램(실제 집계 데이터). open=true 면 counts 의 첫·끝 값은 범위 밖(미만·이상) 구간.
export function histogram(el, { edges, counts, open = false, markers = [], vline = null, title, desc, height = 210, unit = 10000, labelEvery = 0, tick = 0 }) {
  const W = 640, H = height, m = { l: 8, r: 8, t: 22, b: 38 };
  const id = "h" + Math.random().toString(36).slice(2, 8);
  const k = counts.length, bw = (W - m.l - m.r) / k, max = Math.max(...counts, 1);
  const y = v => m.t + (H - m.t - m.b) * (1 - v / max);
  const step = edges[1] - edges[0];
  const man = v => `${Math.round(v / unit).toLocaleString("ko-KR")}만`;
  const xAt = v => {
    if (open) { if (v < edges[0]) return m.l + bw * .5; if (v >= edges[edges.length - 1]) return m.l + bw * (k - .5); return m.l + bw * (1 + (v - edges[0]) / step); }
    return m.l + bw * Math.min(k, Math.max(0, (v - edges[0]) / step));
  };
  let g = counts.map((n, i) => n ? `<rect x="${(m.l + bw * i + 1).toFixed(1)}" y="${y(n).toFixed(1)}" width="${(bw - 2).toFixed(1)}" height="${(H - m.b - y(n)).toFixed(1)}" fill="var(--ink)" opacity=".82"><title>${esc(binLabel(i))}: ${n.toLocaleString("ko-KR")}곳</title></rect>` : "").join("");
  function binLabel(i) {
    if (open) { if (i === 0) return `${man(edges[0])}원 미만`; if (i === k - 1) return `${man(edges[edges.length - 1])}원 이상`; return `${man(edges[i - 1])}~${man(edges[i])}원`; }
    return `${man(edges[i])}~${man(edges[i + 1])}원`;
  }
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--ink)" stroke-width="1"/>`;
  const every = labelEvery || Math.max(1, Math.ceil(edges.length / 7));
  if (tick && !open) {                                  // 값 기준의 둥근 눈금(구간 경계와 무관)
    for (let v = Math.ceil(edges[0] / tick) * tick; v <= edges[edges.length - 1]; v += tick)
      g += `<text class="axis" x="${xAt(v).toFixed(1)}" y="${H - m.b + 15}" text-anchor="middle">${man(v)}</text><line x1="${xAt(v).toFixed(1)}" x2="${xAt(v).toFixed(1)}" y1="${H - m.b}" y2="${H - m.b + 4}" stroke="var(--ink)"/>`;
  } else edges.forEach((e, j) => { if (j % every === 0 || j === edges.length - 1) { const x = open ? m.l + bw * (j + 1) : m.l + bw * j; g += `<text class="axis" x="${x.toFixed(1)}" y="${H - m.b + 15}" text-anchor="middle">${man(e)}</text>`; } });
  if (vline) { const x = xAt(vline.x), anchor = x > W * .6 ? "end" : "start", dx = anchor === "end" ? -6 : 6;
    g += `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${m.t - 6}" y2="${H - m.b}" stroke="var(--s2)" stroke-width="2" stroke-dasharray="5 4"/><text x="${(x + dx).toFixed(1)}" y="${m.t - 8}" text-anchor="${anchor}" font-size="11" font-weight="700" fill="var(--ink)">${esc(vline.label)}</text>`; }
  markers.forEach((mk, i) => { const x = xAt(mk.x);
    g += `<path d="M${(x - 5).toFixed(1)},${H - m.b + 22} L${(x + 5).toFixed(1)},${H - m.b + 22} L${x.toFixed(1)},${H - m.b + 12} Z" fill="var(--accent)"><title>${esc(mk.label)}: ${esc(man(mk.x))}원</title></path>`; });
  const rows = counts.map((n, i) => `<tr><th scope="row">${esc(binLabel(i))}</th><td class="num">${n.toLocaleString("ko-KR")}</td></tr>`).join("");
  el.innerHTML = `<figure class="chart" role="group" aria-labelledby="${id}t"><figcaption id="${id}t"><b>${esc(title)}</b></figcaption>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(desc)}">${g}</svg>
    ${markers.length ? `<div class="legend">${markers.map(mk => `<span><i style="background:var(--accent);height:8px;width:8px;border-radius:50%"></i>${esc(mk.label)} ${esc(man(mk.x))}원</span>`).join("")}</div>` : ""}
    <p class="disclaimer">${esc(desc)}</p>
    <details class="data"><summary>데이터 표로 보기</summary><div class="tablewrap"><table><thead><tr><th>구간</th><th class="num">사업장 수</th></tr></thead><tbody>${rows}</tbody></table></div></details></figure>`;
}
