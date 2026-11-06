import { chrome, esc, getJSON } from "./common.js?v=1f6a6aec9c";
import { KIND, binTable, chartGeom, filterItems, fmtMan, fmtN, fmtPct, lastOverFirst, optionLabel, series, vsAll } from "./lab-core.js?v=1f6a6aec9c";

chrome("lab.html");
const $ = id => document.getElementById(id);
const st = { kind: "industry", id: null, bin: 4, cmp: "" };
let LAB;

const items = () => LAB[st.kind];
const get = id => items().find(it => String(it.id) === String(id));
const bins = () => LAB.meta.bins[KIND[st.kind].binsKey];

function fillOptions(sel, list, current, blank) {
  const opt = list.map(it => `<option value="${it.id}">${esc(optionLabel(it))}</option>`).join("");
  sel.innerHTML = (blank ? `<option value="">비교 안 함</option>` : "") + (opt || `<option value="" disabled>일치하는 분류 없음</option>`);
  const keep = list.some(it => String(it.id) === String(current));
  sel.value = keep ? String(current) : (blank ? "" : list[0] ? String(list[0].id) : "");
  return sel.value;
}

function renderControls() {
  const k = KIND[st.kind];
  $("kindhint").textContent = `${k.label}을 고르면 ${k.axis} 구간으로 분석합니다. (${k.axis}: ${k.hint})`;
  $("binlegend").textContent = `${k.axis} 구간 선택`;
  $("bins").innerHTML = bins().map((b, i) => `<label><input type="radio" name="bin" value="${i}" ${i === st.bin ? "checked" : ""}><span>${esc(b)}</span></label>`).join("");
  const list = filterItems(items(), $("q").value);
  st.id = fillOptions($("cls"), list, st.id, false);
  $("qstat").textContent = $("q").value ? `${list.length}개 분류가 검색됩니다.` : `${items().length}개 분류`;
  st.cmp = fillOptions($("cmp"), items(), st.cmp, true);
}

function chartSvg(its) {
  const Wd = Math.max(300, Math.min(640, window.innerWidth - 48)), sers = its.map(series), g = chartGeom(sers, { W: Wd, H: Math.round(Wd * (Wd < 480 ? 0.85 : 0.5)), m: { l: Wd < 480 ? 44 : 56, r: 12, t: 20, b: 52 } }), cols = ["var(--s1)", "var(--s2)"], B = bins();
  const grid = g.ticks.map(t => `<line x1="${g.m.l}" x2="${g.W - g.m.r}" y1="${t.y.toFixed(1)}" y2="${t.y.toFixed(1)}" stroke="var(--grid)"/><text class="axis" x="${g.m.l - 6}" y="${(t.y + 4).toFixed(1)}" text-anchor="end">${Math.round(t.v).toLocaleString("ko-KR")}</text>`).join("");
  const xs = B.map((b, i) => { const [a, c] = b.split("년"); return `<text class="axis" x="${g.x(i).toFixed(1)}" y="${g.H - 30}" text-anchor="middle"><tspan x="${g.x(i).toFixed(1)}" dy="0">${esc(a)}년</tspan><tspan x="${g.x(i).toFixed(1)}" dy="14">${esc(c)}</tspan></text>`; }).join("");
  const lines = g.series.map((s, k) => s.segs.map(seg => seg.length > 1 ? `<polyline points="${seg.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}" fill="none" stroke="${cols[k]}" stroke-width="2" stroke-dasharray="5 4" opacity=".75"/>` : "").join("")
    + s.pts.map(p => p ? `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${p.i === st.bin ? 7 : 5}" fill="${cols[k]}" ${p.i === st.bin ? 'stroke="var(--ink)" stroke-width="2"' : ""}><title>${esc(its[k].name)} ${esc(B[p.i])}: ${fmtMan(p.v)}</title></circle>` : "").join("")).join("");
  const desc = its.map((it, k) => `${it.name}: ` + sers[k].map((v, i) => `${B[i]} ${v == null ? "자료 없음" : fmtMan(v)}`).join(", ")).join(" / ");
  return `<svg viewBox="0 0 ${g.W} ${g.H}" role="img" aria-label="${esc(`${KIND[st.kind].axis} 5개 구간별 연환산 임금 수준. ${desc}`)}">
    <text class="axis" x="${g.m.l}" y="10">연환산 임금 수준 (만원)</text>${grid}${xs}${lines}</svg>`;
}

function render() {
  const it = get(st.id), cp = st.cmp ? get(st.cmp) : null;
  if (!it) { $("out").innerHTML = `<div class="empty-state">조건에 맞는 분류가 없습니다.</div>`; return; }
  const k = KIND[st.kind], B = bins(), r = vsAll(it, st.bin), tbl = binTable(it, B, st.bin), lof = lastOverFirst(it);
  const diffTxt = r.diff == null ? "비교할 값이 없습니다(비공개·자료 없음)" : `${r.diff >= 0 ? "+" : "−"}${fmtMan(Math.abs(r.diff))} (${fmtPct(r.pct)})`;
  const legend = cp ? `<p class="lab-legend"><span style="--c:var(--s1)">${esc(it.name)}</span><span style="--c:var(--s2)">${esc(cp.name)}</span></p>` : "";
  $("out").innerHTML = `
  <section class="card lab-result" aria-labelledby="rt"><h2 id="rt">${esc(it.name)} · ${esc(k.axis)} ${esc(B[st.bin])}</h2>
    <p class="lab-big"><span class="big">${r.v == null ? "비공개·자료 없음" : fmtMan(r.v)}</span><small>연환산 임금 수준 (월임금총액×12)</small></p>
    <dl class="lab-kv"><div><dt>같은 분류 전체 평균</dt><dd>${fmtMan(r.all)}</dd></div>
      <div><dt>전체 평균과의 차이</dt><dd>${diffTxt}</dd></div>
      <div><dt>이 구간 근로자 수</dt><dd>${fmtN(it.n[st.bin])}</dd></div>
      <div><dt>마지막 구간 ÷ 첫 구간</dt><dd>${lof == null ? "계산 불가" : lof.toFixed(2) + "배"}</dd></div></dl>
    <p class="disclaimer">실제 개인의 연봉이 아니라 조사 기준에 따른 구간 평균입니다. ${esc(B[st.bin])} 안의 개별 연차 값은 알 수 없습니다.</p>
  </section>
  <section class="card" style="margin-top:12px" aria-labelledby="ct"><h2 id="ct">${esc(k.axis)} 5개 구간의 임금 수준</h2>${legend}
    <div class="lab-chart">${chartSvg(cp ? [it, cp] : [it])}</div>
    <p class="disclaimer">점은 공식 ${esc(k.axis)} 5개 구간의 평균입니다. 점을 잇는 점선은 구간의 순서를 보여줄 뿐 개별 연차의 연속적인 임금 상승을 뜻하지 않습니다. 비공개·누락 구간은 점을 찍지 않고 선을 끊습니다.</p>
  </section>
  <section class="card" style="margin-top:12px" aria-labelledby="tt"><h2 id="tt">${esc(it.name)}: 구간별 비교</h2>
    <div class="tablewrap"><table><caption class="vh">${esc(it.name)} ${esc(k.axis)} 구간별 연환산 임금 수준</caption>
    <thead><tr><th scope="col">${esc(k.axis)}</th><th scope="col" class="num">연환산(만원)</th><th scope="col" class="num">선택 구간 대비</th><th scope="col" class="num">근로자 수</th></tr></thead>
    <tbody>${tbl.map(t => `<tr ${t.selected ? 'aria-current="true" style="font-weight:800"' : ""}><th scope="row">${esc(t.label)}${t.selected ? " (선택)" : ""}</th><td class="num">${t.v == null ? "비공개·자료 없음" : fmtMan(t.v)}</td><td class="num">${t.selected ? "-" : fmtPct(t.vsSel)}</td><td class="num">${fmtN(t.n)}</td></tr>`).join("")}</tbody></table></div>
    <p class="disclaimer">출처: 고용노동부 고용형태별노동실태조사 ${LAB.meta.year}년, 성별 전체. ${esc(k.label)} 분류: ${esc(it.raw)}</p>
  </section>`;
}

let rz; window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => LAB && render(), 150); });
function onChange() { renderControls(); render(); }
document.querySelectorAll('input[name="kind"]').forEach(r => r.addEventListener("change", e => { st.kind = e.target.value; st.id = null; st.cmp = ""; $("q").value = ""; onChange(); }));
$("q").addEventListener("input", () => { renderControls(); render(); });
$("cls").addEventListener("change", e => { st.id = e.target.value; render(); });
$("cmp").addEventListener("change", e => { st.cmp = e.target.value; render(); });
$("bins").addEventListener("change", e => { if (e.target.name === "bin") { st.bin = +e.target.value; render(); } });

getJSON("lab/lab.json").then(d => { LAB = d; const f = items().find(it => it.level === "전체"); st.id = f ? f.id : items()[0].id; onChange(); })
  .catch(e => { $("out").innerHTML = `<div class="empty-state">자료를 불러오지 못했습니다: ${esc(e.message)}</div>`; });
