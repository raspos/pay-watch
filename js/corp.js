// 법인(회사) 뷰: 공시 1인 평균급여(DART, 파생값)와 국민연금 추정(확인된 사업장 합산)을 별도 카드로 구분해 보여준다.
import { pickRepresentative, visibleDartAvg } from "./pay-source.js?v=fe815e7e7c";
import { avatar, barChart, capAnnual, esc, fmtInt, fmtMan, fmtPct, gauge, getJSON, histogram, last, lineChart, sparkline, ymShort } from "./common.js?v=fe815e7e7c";

export async function getCorp(code) {
  const sh = await getJSON(`corp/${Number(code) % 128}.json`);
  return sh[code] || null;
}
const shortName = n => String(n).replace(/\(주\)|주식회사|㈜/g, "").trim();
const LVL = { ok: "일관성 확인", caution: "일관성 주의", unverified: "검증 불가" };


// 대표 평균연봉 블록(법인 화면·상세 없는 기업·사람인 전용 기업 공통). DART 공시와 사람인 추정을 숫자 가까이에서 명확히 구분한다.
function repBlockHtml(rep, d) {
  if (rep.kind === "value" && rep.source === "dart") {
    return `<p class="rep-label">평균연봉</p><p class="rep-num">${fmtMan(rep.value)}</p>
       <p class="rep-src">DART 공시 · ${esc(rep.year)}년 · ${esc(rep.scope)}${rep.href ? ` · <a href="${esc(rep.href)}" rel="noopener">원문</a>` : ""}</p>
       <p class="rep-note">친구 개인의 실제 연봉이 아니라 회사 전체 평균입니다.${d && d.tenure != null ? ` 평균근속 ${d.tenure}년, 직원 ${fmtInt(d.employees)}명.` : d ? ` 직원 ${fmtInt(d.employees)}명.` : ""}</p>`;
  }
  if (rep.kind === "value") {
    return `<p class="rep-label">평균연봉 <span class="tag est">사람인 추정</span></p><p class="rep-num">${fmtMan(rep.value)}</p>
       <p class="rep-src">사람인 추정 · 표시연도 ${esc(rep.year)}년</p>
       <p class="rep-note">공시값이 아닌 추정치이며 표시연도가 실제 관측연도와 다를 수 있습니다. 회사 전체 평균이며 개인의 실제 연봉이 아닙니다.${rep.reason === "dart_held_quality" ? " 공시 급여는 확인 중이라 사람인 추정을 보여줍니다." : ""}</p>`;
  }
  return `<p class="rep-label">평균연봉</p><p class="rep-none">${rep.kind === "hold" ? "자료 확인 중" : "자료 없음"}</p><p class="rep-note">${esc(rep.kind === "hold" ? rep.why : "공시 평균급여·사람인 평균연봉 자료가 없어 가상의 값은 표시하지 않습니다.")}</p>`;
}

export function renderCorp(c, meta, app) {
  const name = shortName(c.n), d = c.dart, n = c.nps, labels = meta.months.map(ymShort);
  const capNear = n.cap != null && n.cap >= 0.9;
  const dartOk = d && d.level === "ok";
  const dv = visibleDartAvg(c);                          // 보류된 공시 평균급여는 어떤 숫자·그래프에도 쓰지 않는다(null)
  const scopeOff = c.scope != null && (c.scope < 0.7 || c.scope > 1.3);

  const npsCard = n.est != null
    ? `<div class="kpi card ${capNear ? "warn-card" : ""}"><div class="label">국민연금 기반 연환산 추정금액 <span class="tag est">추정</span>${capNear ? '<span class="tag warn">상한 접근: 하한값</span>' : ""}</div>
        <div class="value">${fmtMan(n.est)}</div>
        <div class="sub">기준월 ${esc(c.ym)}, 확인된 사업장 ${c.n_wp}곳, 가입자 ${fmtInt(n.subs)}명</div>${sparkline(n.series.est)}</div>`
    : `<div class="kpi card na"><div class="label">국민연금 기반 연환산 추정금액 <span class="tag est">추정</span></div><div class="value">계산 불가</div><div class="sub">추정에 쓸 수 있는 확인된 사업장(가입자 10명 이상)이 없습니다.</div></div>`;
  const posLines = [];
  if (d && d.pos) posLines.push(`같은 업종 공시 기업 ${fmtInt(d.pos.n)}곳 중 <b>상위 ${d.pos.top_pct}%</b>(직원 ${esc(d.pos.size)} 구간, 공시 기준끼리 비교)`);
  if (c.pos_nps && c.pos_nps.premium != null) posLines.push(`대표 사업장 기준, 비슷한 규모의 기업(${fmtInt(c.pos_nps.n)}곳)보다 국민연금 추정급여가 <b>${fmtPct(c.pos_nps.premium, 0)}</b>${c.pos_nps.censored ? ' <span class="tag warn">상한 절단: 실제와 순위가 다를 수 있음</span>' : ""}`);
  const first = c.wps[0];
  // 공시 대 추정 짝 막대: 실제 값으로만 그린다(없는 값은 그리지 않음). 점선은 기준소득월액 상한의 연환산.
  const capYr = capAnnual(meta, c.ym);
  const bars = [dv, n.est, capYr].filter(v => v != null);
  const mx = bars.length ? Math.max(...bars) * 1.06 : 1, wd = v => (v / mx * 100).toFixed(1);
  const pair = (dartOk && n.est != null) ? `<div class="pairbars" role="img" aria-label="공시 1인 평균급여 ${d ? fmtMan(dv) : "자료 없음"}, 국민연금 추정 ${n.est != null ? fmtMan(n.est) : "계산 불가"}${capYr ? `, 기준소득월액 상한 연환산 ${fmtMan(capYr)}` : ""}">
      ${d ? `<span class="pl">공시 평균급여</span><span class="pt"><i class="dart" style="width:${wd(dv)}%"></i>${capYr ? `<u style="left:${wd(capYr)}%"></u>` : ""}</span><span class="pv">${fmtMan(dv)}</span>` : ""}
      ${n.est != null ? `<span class="pl">국민연금 추정</span><span class="pt"><i class="nps" style="width:${wd(n.est)}%"></i>${capYr ? `<u style="left:${wd(capYr)}%"></u>` : ""}</span><span class="pv">${fmtMan(n.est)}</span>` : ""}
      <p class="capnote">${capYr ? `점선은 국민연금 기준소득월액 상한의 연환산 값(${fmtMan(capYr)})입니다. 추정 막대가 점선에 가까우면 실제 급여는 더 높을 수 있습니다.` : ""}</p></div>` : "";

  const repHtml = repBlockHtml(pickRepresentative(c), d);
  app.innerHTML = `
  <header class="res-head"><h1 id="nm">${esc(name)}</h1>
    <p class="res-sub">${c.listed ? "상장사" : "비상장"} · ${esc(c.loc || "")}</p></header>
  <section class="rep" aria-labelledby="nm" aria-live="polite">${repHtml}</section>
  <div id="exp-slot"></div>
  ${pair ? `<section class="res-chart"><h2 class="res-h">공시와 국민연금 추정 비교</h2>${pair}</section>` : ""}
  <p class="res-actions"><a href="rank.html?add=${c.code}">내 친구들 회사와 비교하기</a> <a href="compare.html?items=c${c.code}">다른 회사와 비교하기</a></p>
  <details class="more"><summary>국민연금 기반 추정과 상세 분석</summary>
    ${scopeOff ? `<p class="disclaimer"><b>집계 범위 차이</b> 확인된 사업장의 가입자 합이 공시 직원 수의 ${(c.scope * 100).toFixed(0)}% 수준이라 국민연금 추정은 확인된 사업장 기준입니다.</p>` : ""}
    <div class="grid g2" style="margin-top:12px">${npsCard}</div>
    ${d && n.est != null ? `<p class="disclaimer">두 값은 기준과 시점이 다릅니다. 공시는 사업연도 ${d.fy}의 상여 등을 포함한 급여이고, 국민연금 추정은 ${esc(c.ym)}의 기준소득월액(상한 적용)을 연환산한 값입니다.</p>` : ""}
    <section style="margin-top:12px"><h3>회사의 상대적 위치</h3>
    ${posLines.length ? `<ul style="margin:0;padding-left:1.2em">${posLines.map(l => `<li>${l}</li>`).join("")}</ul>` : `<p style="margin:0;color:var(--muted)">비교집단(30곳 이상)이 충분하지 않거나 자료 기준이 달라 위치를 표시하지 않습니다.</p>`}</section>
    <div class="tabs" role="tablist" aria-label="상세 정보">
      ${["PAY", "PEOPLE", "COMPARE", "사업장별", "DATA"].map((t, i) => `<button role="tab" id="t-${i}" aria-controls="p-${i}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}">${t}</button>`).join("")}
    </div>
    ${[0, 1, 2, 3, 4].map(i => `<section class="panel" role="tabpanel" id="p-${i}" aria-labelledby="t-${i}" ${i ? "hidden" : ""}></section>`).join("")}
  </details>`;

  const P = i => document.getElementById(`p-${i}`);
  // PAY
  const capYear = meta.months.map(m => capAnnual(meta, m));
  P(0).innerHTML = `<p class="disclaimer"><b>국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다.</b> 기준월 ${esc(c.ym)}, 확인된 사업장 합산.</p>
    <div class="card"><div id="c-pay"></div></div>
    ${n.cap != null ? `<div class="card" style="margin-top:12px"><div class="gauge">${gauge(n.cap)}<div class="txt"><div class="big">상한 접근도 ${n.cap.toFixed(2)}</div><p class="disclaimer">기준소득월액 상한 대비 평균 기준소득월액의 비율입니다. 눈금(0.9) 이상이면 실제 평균급여가 추정치보다 높을 수 있습니다.</p></div></div></div>` : ""}
    <div class="card" style="margin-top:12px"><dl class="facts">
      <dt>공시 1인 평균급여</dt><dd>${dartOk ? `${fmtMan(dv)} <span class="tag rep">공시 기준 계산값</span>` : (c.hold || d ? "확인 중" : "자료 없음")}</dd>
      <dt>국민연금 추정 연환산</dt><dd>${n.est != null ? `${fmtMan(n.est)} <span class="tag est">추정</span>` : "계산 불가"}</dd>
      ${dartOk && n.est != null && !scopeOff ? `<dt>추정 ÷ 공시</dt><dd>${Math.round(n.est / dv * 100)}% <span class="disclaimer">(상한과 상여 미반영 때문에 낮게 나오는 것이 일반적)</span></dd>` : ""}
      <dt>공시 급여 연간 추이</dt><dd>자료 없음 <span class="tag">이전 연도 미수집</span></dd></dl></div>`;
  lineChart(document.getElementById("c-pay"), { labels, series: [{ name: "추정 연환산(확인된 사업장)", values: n.series.est }, { name: "상한 연환산", values: capYear, dash: true }],
    yFmt: v => fmtMan(v), title: "국민연금 기준소득월액 연환산 추이", desc: "실제 연봉이 매월 오르내린다는 뜻이 아니라 기준소득월액 연환산 값의 추이입니다. 2026-07 상한 인상이 계단으로 보일 수 있습니다." });
  // PEOPLE
  P(1).innerHTML = `<div class="grid g2"><div class="card"><div id="c-subs"></div></div><div class="card"><div id="c-al"></div></div></div>
    <div class="card" style="margin-top:12px"><dl class="facts">
      <dt>국민연금 가입자(확인된 사업장)</dt><dd>${fmtInt(n.subs)}명</dd>
      <dt>공시 직원 수</dt><dd>${d ? `${fmtInt(d.employees)}명 (사업연도 ${d.fy})` : "자료 없음"}</dd>
      ${c.scope != null ? `<dt>집계 범위(가입자÷직원)</dt><dd>${(c.scope * 100).toFixed(0)}%</dd>` : ""}
      <dt>12개월 가입자 증감</dt><dd>${n.g12 != null ? `${fmtPct(n.g12)} (${n.net12 > 0 ? "+" : ""}${fmtInt(n.net12)}명, 두 시점 모두 있는 사업장 기준)` : "계산 불가"}</dd>
      <dt>평균 근속연수</dt><dd>${d && d.tenure != null ? `${d.tenure}년 (공시, 직원 수 가중평균)` : "자료 없음"}</dd></dl></div>
    <p class="disclaimer">국민연금 가입자 수는 회사 전체 직원 수와 같지 않으며, 취득자에는 납부재개, 상실자에는 납부예외가 포함됩니다.</p>`;
  lineChart(document.getElementById("c-subs"), { labels, series: [{ name: "가입자 수", values: n.series.subs }], yFmt: fmtInt, title: "국민연금 가입자 수(확인된 사업장 합계)", desc: "사업장 단위 합계이며 회사 전체 직원 수와 같지 않습니다." });
  barChart(document.getElementById("c-al"), { labels, series: [{ name: "신규 취득자", values: n.series.acq }, { name: "상실 가입자", values: n.series.lost }], title: "취득자·상실자", desc: "취득에는 납부재개, 상실에는 납부예외가 포함됩니다." });
  // COMPARE
  const pos = d && d.pos;
  P(2).innerHTML = `${pos ? (() => { const lo = Math.min(pos.p25, dv) * .85, hi = Math.max(pos.p75, dv) * 1.15, at = v => ((v - lo) / (hi - lo) * 100).toFixed(1);
      return `<div class="card"><h2>공시 기준 동종업계 위치</h2><p class="disclaimer">공시 급여(파생값)를 가진 같은 업종·직원 규모 기업 ${fmtInt(pos.n)}곳과 비교합니다(업종코드 앞 ${pos.level}자리, 직원 ${esc(pos.size)}).</p>
      <div class="band" role="img" aria-label="비교집단 25~75% ${fmtMan(pos.p25)}~${fmtMan(pos.p75)}, 중앙값 ${fmtMan(pos.median)}, 이 회사 ${fmtMan(dv)}"><div class="track"></div><div class="iqr" style="left:${at(pos.p25)}%;width:${at(pos.p75) - at(pos.p25)}%"></div><div class="med" style="left:${at(pos.median)}%"></div><div class="me" style="left:${at(dv)}%"></div></div>
      <p class="disclaimer">파란 칸은 25~75% 구간, 검은 선은 중앙값(${fmtMan(pos.median)}), 주황 선은 이 회사(${fmtMan(dv)})입니다. 상위 ${pos.top_pct}%.</p></div>
      ${pos.hist ? `<div class="card" style="margin-top:12px"><div id="c-hist"></div></div>` : ""}`; })() : `<div class="empty-state">공시 기준 비교집단(30곳 이상)이 없거나 일관성 검증을 통과하지 못해 공시 기준 위치를 표시하지 않습니다.</div>`}
    <div class="card" style="margin-top:12px"><h2>국민연금 추정 기준 위치(대표 사업장)</h2>${c.pos_nps && c.pos_nps.premium != null
      ? `<p>${esc(c.pos_nps.label || "")} 비교집단 ${fmtInt(c.pos_nps.n)}곳 중앙값 대비 <b>${fmtPct(c.pos_nps.premium, 0)}</b>${c.pos_nps.pct != null ? `, ${Math.round(c.pos_nps.pct * 100)}번째 백분위` : ""}.</p>${c.pos_nps.censored ? `<div class="notice" role="note"><strong>상한 영향</strong> 상한에 걸려 순위와 프리미엄이 실제보다 낮게 나옵니다.</div>` : ""}<p class="disclaimer">대표 사업장(<a href="company.html?id=${c.pos_nps.basis_wp}&amp;view=wp">${esc(c.wps[0].n)}</a>) 기준이며 회사 전체의 순위가 아닙니다.</p>`
      : `<p style="margin:0;color:var(--muted)">비교집단이 충분하지 않아 표시하지 않습니다.</p>`}</div>`;
  if (pos && pos.hist) {                                // 같은 업종 공시 기업 분포에 이 회사 위치 표시(양 끝은 2~98% 범위로 모음)
    const h = pos.hist, edges = Array.from({ length: h.counts.length + 1 }, (_, i) => h.lo + i * h.step);
    histogram(document.getElementById("c-hist"), { edges, counts: h.counts, markers: [{ x: dv, label: name }], height: 190, tick: (edges[edges.length - 1] - edges[0]) > 8e7 ? 2e7 : 1e7,
      title: `같은 업종 공시 기업 ${fmtInt(pos.n)}곳의 1인 평균급여 분포`, desc: `공시 급여(파생값)를 가진 기업만의 분포이며 양 끝은 상·하위 2%를 한 구간으로 모았습니다. 삼각형이 이 회사입니다.` });
  }
  // 사업장별
  P(3).innerHTML = `<p class="disclaimer">확인된 사업장(사업자번호 앞 6자리, 이름, 소재지가 모두 일치한 사업장)만 합산했습니다. 확인되지 않은 사업장은 합산하지 않았습니다.${c.n_wp > c.wps.length ? ` 가입자가 많은 ${c.wps.length}곳만 표시합니다.` : ""}</p>
    <div class="card tablewrap"><table><caption class="vh">확인된 사업장</caption><thead><tr><th scope="col">사업장</th><th scope="col">소재지</th><th scope="col" class="num">가입자</th></tr></thead><tbody>
    ${c.wps.map(w => `<tr><td><a href="company.html?id=${w.id}&amp;view=wp">${esc(w.n)}</a></td><td>${esc(w.loc)}</td><td class="num">${fmtInt(w.subs)}명</td></tr>`).join("")}</tbody></table></div>`;
  // DATA
  P(4).innerHTML = `<div class="card"><dl class="facts">
      <dt>국민연금 출처</dt><dd>${esc(meta.source)}, 기준월 ${esc(c.ym)} (최근 13개월 ${esc(meta.months[0])}~${esc(meta.months[12])})</dd>
      <dt>공시 출처</dt><dd>${d ? `DART 사업보고서 직원현황, 사업연도 ${d.fy}, 결산기준일 ${esc(d.stlm)}. <a href="${esc(d.src)}" rel="noopener">원문 보기</a>` : "해당 없음(공시 자료 없음)"}</dd>
      <dt>법인 연결 근거</dt><dd>${c.match.grades.map(esc).join(", ")}: ${c.match.evidence.map(esc).join(", ")}</dd>
      <dt>방법론 버전</dt><dd>${esc(meta.methodology_version)}</dd></dl></div>
    <div class="card" style="margin-top:12px"><h3>수치 구분</h3><table><thead><tr><th>구분</th><th>의미</th><th>이 화면 예</th></tr></thead><tbody>
      <tr><td><span class="tag rep">공시 기준 계산값</span></td><td>공시 자료로 계산한 값(DART의 급여총액÷직원수)</td><td>공시 1인 평균급여, 평균근속(가중평균)</td></tr>
      <tr><td><span class="tag est">추정</span></td><td>계산식으로 추정한 값</td><td>국민연금 기준소득월액 연환산(고지금액÷가입자÷요율×12)</td></tr>
      <tr><td><span class="tag">원자료</span></td><td>원본에서 직접 확인한 값</td><td>가입자 수, 취득자·상실자 수</td></tr>
      <tr><td><span class="tag">자료 없음</span></td><td>확인할 수 없는 값</td><td>이전 연도 공시 급여, 경영성과 대비 보상</td></tr></tbody></table>
      <p class="disclaimer">공시 급여는 상여 등을 포함하고 국민연금 추정은 기준소득월액(상한 적용)이므로 값이 다릅니다. 계산식과 한계는 <a href="methodology.html">방법론</a>을 보세요.</p></div>`;

  // 탭(키보드: 좌우 화살표, Home/End)
  const tabs = [...app.querySelectorAll('[role="tab"]')];
  const show = t => { tabs.forEach(x => { const on = x === t; x.setAttribute("aria-selected", on); x.tabIndex = on ? 0 : -1; document.getElementById(x.getAttribute("aria-controls")).hidden = !on; }); t.focus(); };
  tabs.forEach((t, i) => { t.addEventListener("click", () => show(t));
    t.addEventListener("keydown", e => { const k = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key]; if (k != null) { e.preventDefault(); show(tabs[(k + tabs.length) % tabs.length]); } }); });
}

// 상세 페이지가 없는 기업(검색 색인에만 있음): 이름과 '자료 없음/확인 중'만 보여준다. 존재하지 않는다고 단정하지 않는다.
export function renderEntity(e, app, extra = {}) {
  const name = shortName(e.legal), c = { dart: extra.dart ? { ...extra.dart, level: "ok" } : null, saramin: extra.saramin || null }, rep = pickRepresentative(c);
  const kind = /^\d{8}$/.test(e.code) ? `c${e.code}` : `s${String(e.code).slice(1)}`;
  app.innerHTML = `<header class="res-head"><h1 id="nm">${esc(e.display || name)}</h1>${e.display && e.display !== e.legal ? `<p class="res-sub">${esc(e.legal)}</p>` : ""}</header>
    <section class="rep" aria-labelledby="nm" aria-live="polite">${repBlockHtml(rep, c.dart)}</section>
    <div id="exp-slot"></div><p class="res-actions"><a href="rank.html?add=${e.code}">내 친구들 회사와 비교하기</a> <a href="compare.html${rep.kind === "value" ? `?items=${kind}` : ""}">다른 회사와 비교하기</a></p>`;
}
