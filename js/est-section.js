// PAY워치 연구용 미리보기: 기업 결과 화면(company.html?corp=코드)에 '근속 구간 집단의 평균급여 · 실험적 추정' 영역을 덧붙인다(연구용 빌드 전용; 공개 site/ 에는 이 파일이 없다).
// 표시 기준(범위 산출·민감도 검토를 통과한 기업만): A 범위 / B 범위 + 간결한 주의 / C·D 영역 자체를 렌더링하지 않는다(데이터에도 범위가 없다).
// 대표 범위는 확대 시나리오, 기본 시나리오는 접이식 상세. 기본 근속 구간은 5~10년(검색 직후 추가 클릭 없음).
import { esc, getJSON } from "./common.js?v=080a125729";
import { BINS, BIN_LABEL, DEFAULT_BIN, WIDE, canEstimate, chartModel, fmtEok, fmtRange, gradeOf, isWide, reasonText, resolveBin, shardOf } from "./est-core.js?v=080a125729";

export async function getFirm(code) { const sh = await getJSON(`est/s/${shardOf(code)}.json`); return sh[code] || null; }

function noteHtml(rec, bin) {
  if (!rec.cau && rec.g !== "B") return "";                                   // 주의 표시가 있는 기업(cau)만
  const why = (rec.w || []).map(reasonText);
  if (rec.h || rec.x == null) why.push("형태 변화 분석을 수행하지 않아 확대 범위가 없습니다.");
  const wide = BINS.some((_, i) => rec.x && isWide(rec.x[i]));
  if (wide) why.push(`확대 범위의 폭이 ${Math.round(WIDE * 100)}%를 넘는 구간이 있습니다(설명용 기준이며 신뢰도 등급이 아닙니다).`);
  return `<details class="xp-why"><summary>가정에 따라 결과가 크게 달라질 수 있습니다 <span>이유 보기</span></summary><ul>${why.map(w => `<li>${esc(w)}</li>`).join("")}</ul></details>`;
}
function binPicker(bin) {
  return `<fieldset class="xp-bins"><legend>근속기간</legend><div>${BIN_LABEL.map((l, i) => `<label><input type="radio" name="xb" value="${i}" ${i === bin ? "checked" : ""}><span>${esc(l)}</span></label>`).join("")}</div></fieldset>`;
}
function chartSvg(rec, bin) {
  const g = chartModel(rec, bin); if (!g) return "";
  const grid = g.ticks.map(t => `<line x1="${g.m.l}" x2="${g.W - g.m.r}" y1="${t.y.toFixed(1)}" y2="${t.y.toFixed(1)}" stroke="var(--grid)"/><text class="xp-ax" x="${g.m.l - 6}" y="${(t.y + 4).toFixed(1)}" text-anchor="end">${esc(fmtEok(t.v))}</text>`).join("");
  const bars = g.bars.map(b => {
    const exp = b.exp ? `<rect x="${(b.x - b.bw / 2).toFixed(1)}" y="${b.ye[0].toFixed(1)}" width="${b.bw}" height="${Math.max(2, b.ye[1] - b.ye[0]).toFixed(1)}" fill="var(--s1)" opacity=".25" rx="2"><title>확대 시나리오 ${esc(BIN_LABEL[b.i])}: ${esc(fmtRange(b.exp))}</title></rect>` : "";
    const base = `<rect x="${(b.x - b.bw * 0.275).toFixed(1)}" y="${b.yb[0].toFixed(1)}" width="${(b.bw * 0.55).toFixed(1)}" height="${Math.max(2, b.yb[1] - b.yb[0]).toFixed(1)}" fill="var(--s1)" opacity=".85" rx="2"><title>기본 시나리오 ${esc(BIN_LABEL[b.i])}: ${esc(fmtRange(b.base))}</title></rect>`;
    const hit = `<rect x="${(b.x - g.W / 10 + 4).toFixed(1)}" y="${g.m.t}" width="${(g.W / 5 - 8).toFixed(1)}" height="${g.H - g.m.t - g.m.b}" fill="${b.selected ? "var(--accent-soft)" : "transparent"}" rx="4"/>`;
    return `<g class="xp-col" data-bin="${b.i}" tabindex="0" role="button" aria-label="${esc(BIN_LABEL[b.i])} 선택">${hit}${exp}${base}<text class="xp-ax" x="${b.x.toFixed(1)}" y="${g.H - 24}" text-anchor="middle" ${b.selected ? 'font-weight="700"' : ""}>${esc(BIN_LABEL[b.i])}</text></g>`;
  }).join("");
  const avg = g.avgY != null ? `<line x1="${g.m.l}" x2="${g.W - g.m.r}" y1="${g.avgY.toFixed(1)}" y2="${g.avgY.toFixed(1)}" stroke="var(--s2)" stroke-width="1.5" stroke-dasharray="6 4"/>` : "";
  const desc = BINS.map((b, i) => `${BIN_LABEL[i]} 기본 ${fmtRange(rec.b[i])}${rec.x ? `, 확대 ${fmtRange(rec.x[i])}` : ""}`).join("; ");
  return `<svg viewBox="0 0 ${g.W} ${g.H}" role="img" aria-label="${esc("근속 5개 구간별 집단 평균급여 시나리오 범위. " + desc)}">${grid}${avg}${bars}</svg>`;
}

function methodHtml() {
  return `<h3 class="xp-h">추정 방법</h3>
    <p><b>기본 시나리오(인력 구성만 반영)</b>는 기업의 평균근속과 산업의 장기근속 공식 통계 범위에 양립하는 인력 구성 가정(두 가지)을 적용해, 같은 산업의 2025년 근속 구간별 임금 곡선을 기업 공시 평균급여에 맞춘 범위입니다.</p>
    <p><b>확대 시나리오(곡선 형태 변화까지 반영)</b>는 여기에 같은 산업의 2020~2024년 곡선과 유사 산업의 2025년 곡선(실제 통계에서 관측된 다른 곡선 형태)을 더 적용한 범위이며 기본 범위를 항상 포함합니다.</p>
    <p>구간은 공식 5개 구간만 쓰며 개별 연차는 보간하지 않습니다. 근속 구간 결과는 월임금총액×12 기준의 연환산 집단 평균입니다.</p>`;
}
function cautionHtml(rec) {
  return `<h3 class="xp-h">주의사항</h3>
    <p>공개된 기업 평균급여와 정부 임금통계를 결합한 시나리오 분석입니다. 실제 개인의 연봉 범위나 검증된 예측구간이 아니며, 개인별 급여 분포도 아닙니다. 모형의 정확도는 검증되지 않았습니다.</p>
    <p>범위가 좁다고 정확하다는 뜻이 아닙니다. 기업별 곡선 모양, 급여 정의 차이(공시 지급총액 vs 노동부 6월 월급여+전년도 특별급여/12), 기업 내부 근속 구성은 관측되지 않았습니다. 범위는 자료가 충분하고 가정 민감도 검토를 통과한 기업에만 표시하며, 이 표시 기준은 예측 정확도를 보증하지 않습니다.</p>
    <p>공공기관 5곳의 공시 신입 초임과 1년 미만 범위를 비교한 참고 점검에서 기본 범위는 2곳, 확대 범위는 5곳을 포함했으나 범위 폭이 2.3~4.5배 넓어진 결과이고 모집단이 달라 정확도 검증이 아닙니다.</p>
    <p class="xp-src">출처: 고용노동부 고용형태별노동실태조사 2020~2025(산업·근속년수·성별 임금 및 근로조건), DART 2025 사업보고서 직원현황. 산업 분류 ${esc(rec.i || "연결 안 됨")}.
    <a href="lab.html">공식 임금통계 LAB</a></p>`;
}

// 다섯 구간의 시나리오 추정 범위를 한눈에(대표 범위 = 확대 시나리오, 없으면 기본). 클릭하면 아래 큰 숫자·그래프가 바뀐다.
function tableHtml(rec, bin) {
  return `<ol class="xp-tab" aria-label="근속 구간별 집단 평균급여 시나리오 추정 범위">${BIN_LABEL.map((l, i) => {
    const r = resolveBin(rec, i), m = r.exp || r.base;
    return `<li class="${i === bin ? "on" : ""}"><button type="button" data-bin="${i}" aria-pressed="${i === bin}"><span>${esc(l)}</span><b>${esc(fmtRange(m))}</b></button></li>`;
  }).join("")}</ol>`;
}

function sectionHtml(rec, bin) {
  const r = resolveBin(rec, bin);
  const main = r.exp || r.base, mainNote = r.exp ? "곡선 형태 변화까지 반영한 대표 범위" : "인력 구성만 반영(곡선 형태 분석을 수행하지 않아 확대 범위 없음)";
  return `<section class="xp-sec" aria-labelledby="xr">
    <p class="xp-flag"><span>연구용</span> 공식 공시값이 아닌 모형 추정입니다</p>
    <h2 id="xr" class="xp-kicker">근속 구간 집단의 평균급여 · 실험적 추정</h2>
    ${tableHtml(rec, bin)}
    <p class="xp-big" aria-live="polite"><span class="vh">근속 ${esc(BIN_LABEL[bin])}: </span>${esc(fmtRange(main))}</p>
    <p class="xp-cap">근속 ${esc(BIN_LABEL[bin])} · ${esc(mainNote)} · 개인 연봉이나 통계적 신뢰구간이 아니며 정확도는 검증되지 않았습니다</p>
    ${noteHtml(rec, bin)}
    <div class="xp-chartbox">${chartSvg(rec, bin)}<p class="xp-legend"><span class="sw base"></span>기본 <span class="sw exp"></span>확대 ${rec.a != null ? '<span class="sw avg"></span>기업 전체 평균(공시)' : ""}${(chartModel(rec, bin) || {}).zeroBased ? "" : " · 세로축은 0에서 시작하지 않음"}</p></div>
    <details class="xp-det"><summary>출처 · 추정 방법 · 주의사항</summary>
      <p><b>출처</b>: 고용노동부 고용형태별노동실태조사 산업·근속 구간별 임금 + 이 회사의 DART 공시 평균급여·평균근속(${esc(rec.y || 2025)}년 기준, 모형 ${esc(rec.m || "")}).</p>
      <p><b>기본 시나리오</b>(인력 구성만 반영) 근속 ${esc(BIN_LABEL[bin])}: ${esc(fmtRange(r.base))}</p>
      ${methodHtml()}${cautionHtml(rec)}</details>
    </section>`;
}

/** 공시 평균급여가 보류된 기업(dartOk === false)은 기업 전체 평균(rec.a)을 그래프 데이터에서 뺀다(기준선·축 범위 모두). 원본 rec 는 바꾸지 않는다. */
export function effectiveRec(rec, opts = {}) {
  if (opts.dartAvgMan !== undefined) return { ...rec, a: opts.dartAvgMan };            // 공개 데이터에는 기업 평균(a)이 없다 — 결과 화면이 보여도 되는 DART 평균(만원)만 받아 쓴다(보류 기업은 null)
  return opts.dartOk === false ? { ...rec, a: null } : rec;
}

/** slot 에 영역을 그린다. A·B 등급이 아니거나 데이터가 없으면 아무것도 렌더링하지 않는다(빈 안내 카드 없음). */
export async function mountEstimate(slot, code, opts = {}) {
  slot.innerHTML = "";
  let rec = null; try { rec = await getFirm(code); } catch { /* 추정 데이터를 읽지 못하면 아래 안내 */ }
  if (!rec || !canEstimate(rec)) {                                         // 추정 불가 기업: 숫자를 만들지 않고 한 줄 안내만(빈 카드 없음)
    slot.innerHTML = '<p class="xp-none">근속 구간별 추정 연봉은 공시 평균급여·평균근속이 확인되고 계산 조건을 충족한 기업에만 제공합니다. 이 회사는 해당 조건을 충족하지 못해 숫자를 만들지 않았습니다.</p>';
    return;
  }
  rec = effectiveRec(rec, opts);                                          // 공시 평균급여가 보류된 기업: 기업 전체 평균 선을 그리지 않는다
  let bin = DEFAULT_BIN;
  const draw = () => {
    slot.innerHTML = sectionHtml(rec, bin);
    slot.querySelectorAll(".xp-tab button").forEach(b => b.addEventListener("click", () => { bin = +b.dataset.bin; draw(); }));
    slot.querySelectorAll(".xp-col").forEach(g => {
      const pick = () => { bin = +g.dataset.bin; draw(); };
      g.addEventListener("click", pick); g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
    });
  };
  draw();
}
