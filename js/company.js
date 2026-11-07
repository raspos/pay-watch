import { capAnnual, BADGE_KO, FLAG_KO, GRADE_INFO, PCR_KO, avatar, barChart, chrome, gauge, sparkline, esc, fmtInt, fmtMan, fmtPct, getDetail, getJSON, getMeta, last, lineChart, ymShort } from "./common.js?v=a343786488";
import { mountFinder } from "./finder-ui.js?v=a343786488";
import { resultHref } from "./finder-core.js?v=a343786488";
import { searchTop } from "./search.js?v=a343786488";
import { getCorp, renderCorp, renderEntity } from "./corp.js?v=a343786488";
import { loadEntities } from "./finder-ui.js?v=a343786488";
import { getSaramin } from "./saramin.js?v=a343786488";
import { visibleDartAvg } from "./pay-source.js?v=a343786488";

chrome("");
mountFinder(document.getElementById("search"), { placeholder: "회사 이름을 검색하세요", label: "회사 검색", nps: async q => (await searchTop(q, 6)).list,
  onPick: it => { location.href = it.kind === "wp" ? `company.html?id=${it.w.id}` : resultHref(it.e); } });
const app = document.getElementById("app");
const q = new URLSearchParams(location.search);
const id = q.get("id"), corp = q.get("corp"), view = q.get("view"), sm = q.get("sm");

(async () => {
  if (!id && !corp && !sm) { app.innerHTML = `<div class="empty-state">위 검색창에서 회사를 선택하세요.</div>`; return; }
  if (sm) {                                              // 사람인에만 있는 기업(DART 코드 없음): 사람인 공개 id 로 같은 결과 화면
    const e = /^S[0-9a-f]{10}$/.test(sm) ? (await loadEntities()).find(x => x.code === sm) : null;
    if (!e) { app.innerHTML = `<div class="empty-state">검색 색인에서 해당 회사를 찾지 못했습니다. 이름의 일부로 다시 검색해 주세요.</div>`; return; }
    document.title = `${e.display || e.legal} | 내 친구는 얼마벌까?`;
    renderEntity(e, app, { saramin: await getSaramin(sm) });
    return;
  }
  const meta = await getMeta();
  if (corp) {                                            // 법인(회사) 뷰: 공시 + 확인된 사업장 합산
    const c = await getCorp(corp);
    if (!c) {                                            // 상세 페이지가 없는 기업: 검색 색인의 이름으로 '자료 없음' 결과를 보여준다
      const e = /^\d{8}$/.test(corp) ? (await loadEntities()).find(x => x.code === corp) : null;
      if (e) { document.title = `${e.display || e.legal} | 내 친구는 얼마벌까?`; const only = await getJSON("finder/dart_only.json").catch(() => ({})); renderEntity(e, app, { dart: only[corp] || null, saramin: await getSaramin(corp) }); window.__pwResult = { code: corp, dartOk: !!only[corp], dartAvg: only[corp] ? only[corp].avg : null }; window.dispatchEvent(new CustomEvent("pw:result", { detail: window.__pwResult })); return; }
      app.innerHTML = `<div class="empty-state">검색 색인에서 해당 회사를 찾지 못했습니다. 이름의 일부로 다시 검색해 주세요.</div>`; return;
    }
    document.title = `${c.n.replace(/\(주\)|주식회사|㈜/g, "").trim()} 다니는 친구는 얼마나 벌까? | 내 친구는 얼마벌까?`;
    c.saramin = await getSaramin(corp);                   // 사람인 값은 DART 값과 별도로 보존(덮어쓰지 않음). 대표값 선택은 pay-source.js
    renderCorp(c, meta, app);
    window.__pwResult = { code: corp, dartOk: !!(c.dart && c.dart.level === "ok"), dartAvg: visibleDartAvg(c) };   // 이벤트보다 늦게 로드된 연구용 로더도 읽을 수 있게 먼저 기록
    window.dispatchEvent(new CustomEvent("pw:result", { detail: window.__pwResult }));   // 연구용 미리보기가 같은 화면에 근속 추정을 덧붙이는 신호(공개 빌드에서는 듣는 곳이 없다)
    return;
  }
  const d = await getDetail(id, meta.n_shards);
  if (!d) { app.innerHTML = `<div class="empty-state">해당 사업장을 찾을 수 없습니다. 검색에서 다시 선택해 주세요.</div>`; return; }
  if (d.co && d.co.p && view !== "wp") { location.replace(`company.html?corp=${d.co.c}`); return; }   // 기존 링크(사업장 id)는 회사 뷰로 연결
  document.title = `${d.n} | 내 친구는 얼마벌까?`;
  const inds = await getJSON("industries.json");
  render(d, meta, inds);
})().catch(e => { app.innerHTML = `<div class="empty-state">자료를 불러오지 못했습니다: ${esc(e.message)}</div>`; });

function render(d, meta, inds) {
  const labels = meta.months.map(ymShort);
  const estNow = d.e ? last(d.e) : null;
  const capNow = d.c ? last(d.c) : null;
  const capNear = capNow != null && capNow >= 0.9;
  const subsNow = last(d.s);
  const m = d.m;
  const ind2 = inds[d.i2];

  const pays = d.pp
    ? `<div class="kpi card ${capNear ? "warn-card" : ""}"><div class="label">국민연금 기반 연환산 추정금액 <span class="tag est">추정</span></div><div class="value">${estNow != null ? fmtMan(estNow) : "—"}</div><div class="sub">기준월 ${esc(d.ym)} · 평균 기준소득월액 ×12${capNear ? " · <b>상한 접근: 하한값</b>" : ""}</div>${sparkline(d.e)}</div>`
    : `<div class="kpi card na"><div class="label">국민연금 기반 연환산 추정금액 <span class="tag est">추정</span></div><div class="value">공개 기준 미달</div><div class="sub">가입자 10명 미만 사업장은 개인 급여 노출 우려로 추정치를 공개하지 않습니다.</div></div>`;

  app.innerHTML = `
  <section class="card company-hero" aria-labelledby="nm">
    <div class="head">${avatar(d.n)}<div>
    <h1 id="nm" style="font-size:clamp(24px,5vw,34px);margin:0">${esc(d.n)}</h1></div></div>
    <p style="margin-top:12px">${esc(d.ind)} · ${esc(d.loc)} · ${esc(d.t)}사업장 · 데이터 기준월 <b>${esc(d.ym)}</b>
      ${d.grade ? `<span class="tag ${d.grade === "B" ? "rep" : "warn"}" title="${esc(GRADE_INFO[d.grade])}">품질 등급 ${esc(d.grade)}</span>` : ""}
      ${d.b.map(b => `<span class="tag warn">${esc(BADGE_KO[b] || b)}</span>`).join(" ")}</p>
    <p class="disclaimer">국민연금 가입 사업장 단위 자료입니다. 같은 법인의 다른 사업장은 합산되어 있지 않으며, 가입자 수는 회사 전체 직원 수가 아닙니다. 품질 등급은 데이터의 근거와 활용 가능성에 대한 평가이며 연봉의 정확성을 보증하지 않습니다.</p>
  </section>
  ${d.co ? `<div class="notice" role="note"><strong>회사(법인) 기준 보기</strong> 이 사업장은 DART 법인의 확인된 사업장 중 하나입니다. <a href="company.html?corp=${esc(d.co.c)}">회사 전체 기준(공시 급여 포함)으로 보기</a></div>` : ""}
  ${capNear ? `<div class="notice" role="note"><strong>상한 영향 주의</strong> 국민연금 기준소득월액 상한의 영향으로 실제 평균급여가 추정치보다 높을 수 있습니다.</div>` : ""}
  ${d.ps ? `<div class="notice" role="note"><strong>건설 현장 단위 사업장</strong> 이름 형식으로 보아 회사 전체가 아니라 공사 현장 단위로 등록된 사업장입니다(일용·상용 근로자 중심). 가입자 수와 급여는 그 현장의 값이며, 동종업계 비교와 순위에서는 제외됩니다.</div>` : ""}
  ${m.rs ? `<div class="notice" role="note"><strong>사업장 변동 확인 필요</strong> 최근 12개월 안에 가입자 수가 전월 대비 50% 이상 급변한 달이 있습니다. 합병·분할·재등록일 수 있어 증감 지표를 단정하지 마세요.</div>` : ""}
  <div class="grid g4" style="margin-top:12px">
    ${pays}
    <div class="kpi card na"><div class="label">DART 공시 평균급여 <span class="tag">자료 없음</span></div><div class="value">자료 없음</div><div class="sub">공시 급여(DART)는 아직 연동되지 않아 확인되지 않았습니다. 추정금액과 별도 카드로 구분해 표시합니다.</div></div>
    <div class="kpi card"><div class="label">국민연금 가입자 수 <span class="tag rep">원자료</span></div><div class="value">${fmtInt(subsNow)}명</div><div class="sub">전월 대비 ${fmtPct(m.mom)}</div>${sparkline(d.s, { color: "var(--g3)" })}</div>
    <div class="kpi card"><div class="label">최근 12개월 가입자 증감 <span class="tag">계산</span></div><div class="value">${m.g12 != null ? fmtPct(m.g12) : "—"}</div><div class="sub">${m.net12 != null ? `순증감 ${m.net12 > 0 ? "+" : ""}${fmtInt(m.net12)}명` : "12개월 전 가입자 10명 미만 또는 자료 부족으로 계산하지 않음"}</div></div>
  </div>
  <div class="tabs" role="tablist" aria-label="상세 정보">
    ${["PAY", "PEOPLE", "COMPARE", "PERFORMANCE", "DATA"].map((t, i) => `<button role="tab" id="t-${t}" aria-controls="p-${t}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}">${t}</button>`).join("")}
  </div>
  <section class="panel" role="tabpanel" id="p-PAY" aria-labelledby="t-PAY"></section>
  <section class="panel" role="tabpanel" id="p-PEOPLE" aria-labelledby="t-PEOPLE" hidden></section>
  <section class="panel" role="tabpanel" id="p-COMPARE" aria-labelledby="t-COMPARE" hidden></section>
  <section class="panel" role="tabpanel" id="p-PERFORMANCE" aria-labelledby="t-PERFORMANCE" hidden></section>
  <section class="panel" role="tabpanel" id="p-DATA" aria-labelledby="t-DATA" hidden></section>`;

  // ---- PAY ----
  const pay = document.getElementById("p-PAY");
  if (d.pp) {
    const capYear = meta.months.map((m, i) => d.e[i] != null ? capAnnual(meta, m) : null);
    pay.innerHTML = `<p class="disclaimer"><b>국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다.</b> 기준월 ${esc(d.ym)}.</p>
      <div class="card"><div id="ch-pay"></div></div>
      ${capNow != null ? `<div class="card" style="margin-top:12px"><div class="gauge">${gauge(capNow)}<div class="txt"><div class="big">상한 접근도 ${capNow.toFixed(2)}</div><p class="disclaimer">기준소득월액 상한 대비 평균 기준소득월액의 비율입니다. 눈금(0.9) 이상이면 실제 평균급여가 추정치보다 높을 수 있습니다.</p></div></div></div>` : ""}
      <div class="card" style="margin-top:12px"><dl class="facts">
        <dt>평균 기준소득월액(추정)</dt><dd>${fmtMan(estNow / 12)} <span class="tag est">추정</span></dd>
        <dt>상한 접근도</dt><dd>${capNow != null ? capNow.toFixed(3) : "—"} <span class="disclaimer">(1.0 = 기준소득월액 상한. 0.9 이상이면 주의)</span></dd>
        <dt>12개월 추정급여 변화율</dt><dd>${m.pc12 != null ? fmtPct(m.pc12) : "계산하지 않음"} <span class="disclaimer">${m.pc12 == null ? esc(PCR_KO[m.pcr] || "") : "직원 구성 변화 등이 섞인 값이며 임금 인상률이 아닙니다"}</span></dd>
        <dt>DART 공시 평균급여 연간 추이</dt><dd>자료 없음 <span class="tag">미연동</span></dd>
      </dl></div>
      <p class="disclaimer">월별 선은 실제 연봉이 매월 오르내린다는 뜻이 아니라, 국민연금 기준소득월액을 연환산한 값의 추이입니다. 2026-07에 상한이 637만원에서 659만원으로 바뀐 영향이 상한 접근 사업장의 선에 계단으로 나타날 수 있습니다.</p>`;
    lineChart(document.getElementById("ch-pay"), { labels, series: [
      { name: "추정 연환산(기준소득월액×12)", values: d.e }, { name: "상한 연환산", values: capYear, dash: true }],
      yFmt: v => fmtMan(v), title: "국민연금 기준소득월액 연환산 추이", desc: "점선은 해당 월의 기준소득월액 상한을 연환산한 값입니다(설정된 상한액 × 12)." });
  } else pay.innerHTML = `<div class="empty-state">이 사업장은 국민연금 가입자 10명 미만이라 추정급여를 공개하지 않습니다. 가입자 수 변화는 PEOPLE 탭에서 볼 수 있습니다.</div>`;

  // ---- PEOPLE ----
  const people = document.getElementById("p-PEOPLE");
  people.innerHTML = `<div class="grid g2"><div class="card"><div id="ch-subs"></div></div><div class="card"><div id="ch-al"></div></div></div>
    <div class="card" style="margin-top:12px"><dl class="facts">
      <dt>전월 대비 가입자</dt><dd>${fmtPct(m.mom)}</dd>
      <dt>3개월 증감</dt><dd>${m.g3 != null ? fmtPct(m.g3) : "계산 불가(3개월 전 가입자 10명 미만)"}</dd>
      <dt>12개월 증감</dt><dd>${m.g12 != null ? fmtPct(m.g12) : "계산 불가"}</dd>
      <dt>12개월 가입자 증가 달 수</dt><dd>${m.up != null ? `${m.up}개월 / 12개월` : "계산 불가(13개월 자료 필요)"}</dd>
      <dt>12개월 누적 상실률</dt><dd>${m.lc12 != null ? fmtPct(m.lc12, 1, false) : "계산 불가"} <span class="disclaimer">상실 가입자 12개월 합 ÷ 평균 가입자. 납부예외 등이 포함돼 <b>실제 퇴사율이 아닙니다</b></span></dd>
      <dt>12개월 누적 취득률</dt><dd>${m.ac12 != null ? fmtPct(m.ac12, 1, false) : "계산 불가"} <span class="disclaimer">납부재개가 포함돼 실제 입사율이 아닙니다</span></dd>
      <dt>평균 근속연수 · 정규직 비중</dt><dd>자료 없음 <span class="tag">DART 미연동</span></dd>
    </dl></div>
    <p class="disclaimer">국민연금 상실률만으로 고용 안정성을 판단할 수 없습니다. 정년퇴직, 사업장 이동, 사업 구조 변화의 영향이 큽니다.</p>`;
  lineChart(document.getElementById("ch-subs"), { labels, series: [{ name: "가입자 수", values: d.s }], yFmt: fmtInt, title: "국민연금 가입자 수 추이", desc: "회사 전체 직원 수와 같지 않습니다." });
  barChart(document.getElementById("ch-al"), { labels, series: [{ name: "신규 취득자", values: d.a }, { name: "상실 가입자", values: d.l }], title: "취득자·상실자 변화", desc: "취득에는 납부재개, 상실에는 납부예외가 포함됩니다." });

  // ---- COMPARE ----
  const cmp = document.getElementById("p-COMPARE");
  if (d.pp && d.peer) {
    const p = d.peer, lo = Math.min(p.p25, estNow) * .85, hi = Math.max(p.p75, estNow) * 1.15, pos = v => ((v - lo) / (hi - lo) * 100).toFixed(1);
    const lvlKo = { 6: "같은 세부 업종(코드 6자리)", 4: "비슷한 업종(코드 앞 4자리)", 2: "넓은 업종 그룹(코드 앞 2자리, 서로 다른 업종이 섞일 수 있음)" }[p.lvl] || "같은 업종";
    const scopeKo = `${lvlKo} · ${p.scope.endsWith("_merged") ? "인접 규모 구간 병합" : "같은 규모 구간"}`;
    cmp.innerHTML = `<p class="disclaimer">국민연금 고지액 기반 추정치 비교입니다. 비교집단: ${scopeKo} ${fmtInt(p.n)}곳, 기준월 ${esc(d.ym)}.</p>
      <div class="card"><h2>동종업계 내 위치</h2>
        <div class="band" role="img" aria-label="비교집단 25~75% 구간 ${fmtMan(p.p25)}~${fmtMan(p.p75)}, 중앙값 ${fmtMan(p.med)}, 이 사업장 ${fmtMan(estNow)}">
          <div class="track"></div><div class="iqr" style="left:${pos(p.p25)}%;width:${pos(p.p75) - pos(p.p25)}%"></div>
          <div class="med" style="left:${pos(p.med)}%" title="중앙값"></div><div class="me" style="left:${pos(estNow)}%" title="이 사업장"></div></div>
        <p class="disclaimer">파란 칸 = 비교집단 25~75% 구간, 검은 선 = 중앙값(${fmtMan(p.med)}), 주황 선 = 이 사업장(${fmtMan(estNow)})</p>
        <dl class="facts"><dt>비교집단 중앙값 대비</dt><dd>${fmtPct(m.prem)} <span class="tag est">PAY PREMIUM</span></dd>
          <dt>비교집단 내 백분위</dt><dd>${m.pct != null ? `${Math.round(m.pct * 100)}번째 백분위` : "—"}${m.cen ? ' <span class="tag warn">상한 절단: 실제는 더 높을 수 있음</span>' : ""}</dd>
          <dt>비교집단</dt><dd>${esc(p.lab || "")} · 가입자 ${esc(p.size)} 구간${p.scope.endsWith("_merged") ? "(인접 구간과 병합)" : ""}</dd></dl></div>
      ${m.cen ? `<div class="notice" role="note"><strong>상한 영향</strong> 이 사업장은 기준소득월액 상한에 접근해 백분위와 프리미엄이 실제보다 낮게 나옵니다. 상한에 걸린 기업끼리의 순위는 의미가 작습니다.</div>` : ""}
      ${ind2 ? `<div class="card" style="margin-top:12px"><h3>참고: 업종 코드 앞 2자리 ‘${esc(d.i2)}’ 그룹 전체 — 표본 ${fmtInt(ind2.n)}곳 <span class="disclaimer">(그룹 안에 여러 업종이 섞여 있어 위 비교집단과 다릅니다)</span></h3><dl class="facts"><dt>추정급여 중앙값</dt><dd>${fmtMan(ind2.med)}</dd><dt>12개월 가입자 증감 중앙값</dt><dd>${fmtPct(ind2.g12)}</dd><dt>12개월 누적 상실률 중앙값</dt><dd>${fmtPct(ind2.lc12, 1, false)}</dd></dl></div>` : ""}`;
  } else cmp.innerHTML = `<div class="empty-state">${d.pp ? "업종 코드가 분류되지 않았거나 비교집단 표본이 30곳 미만이라 동종업계 비교를 제공하지 않습니다." : "추정급여가 공개되지 않는 사업장입니다."}</div>`;

  // ---- PERFORMANCE ----
  document.getElementById("p-PERFORMANCE").innerHTML = `<div class="empty-state"><b>경영성과와 보상 — 자료 없음</b><br>매출·영업이익 대비 급여, 직원 1인당 매출, 임원·직원 보수 격차는 DART 공시 자료가 있어야 계산할 수 있고, 공시 연동은 아직 완료되지 않았습니다. 확인되지 않은 값은 표시하지 않습니다.</div>`;

  // ---- DATA ----
  const flags = d.fl.map(f => `<li>${esc(FLAG_KO[f] || f)}</li>`).join("");
  document.getElementById("p-DATA").innerHTML = `<div class="card"><dl class="facts">
      <dt>출처</dt><dd>${esc(meta.source)}</dd><dt>자료 기준월</dt><dd>${esc(d.ym)} (최근 13개월 ${esc(meta.months[0])}~${esc(meta.months[12])})</dd>
      <dt>방법론 버전</dt><dd>${esc(meta.methodology_version)}</dd><dt>품질 등급</dt><dd>${d.grade ? `${esc(d.grade)} — ${esc(GRADE_INFO[d.grade])}` : "추정급여 비공개 사업장"}</dd></dl></div>
    <div class="card" style="margin-top:12px"><h3>이 화면의 수치 구분</h3><table><thead><tr><th>구분</th><th>의미</th><th>이 사업장 예</th></tr></thead><tbody>
      <tr><td><span class="tag rep">원자료</span></td><td>원본 파일에서 직접 확인한 값</td><td>가입자 수, 신규 취득자·상실자 수</td></tr>
      <tr><td><span class="tag est">추정</span></td><td>계산식으로 추정한 값</td><td>기준소득월액 연환산(고지금액 ÷ 가입자 ÷ 보험료율 × 12)</td></tr>
      <tr><td><span class="tag">계산</span></td><td>확인된 값으로 산출한 통계</td><td>12개월 증감률, 비교집단 중앙값, 백분위</td></tr>
      <tr><td><span class="tag">자료 없음</span></td><td>자료 부족으로 확인할 수 없는 값</td><td>DART 공시 평균급여, 평균 근속, 재무 성과</td></tr></tbody></table></div>
    <div class="card" style="margin-top:12px"><h3>품질 경고</h3>${flags ? `<ul>${flags}</ul>` : "<p>표시할 경고가 없습니다(경고가 없다는 것이 추정이 정확하다는 뜻은 아닙니다).</p>"}
      <p class="disclaimer">원자료 확인: 공공데이터포털 파일 ‘${esc(meta.source)}’의 ${esc(d.ym)} 파일에서 사업장명 ‘${esc(d.n)}’을 찾아 가입자수·당월고지금액을 대조할 수 있습니다. 계산식과 한계는 <a href="methodology.html">방법론</a>을 보세요.</p></div>`;

  // ---- 탭(키보드: 좌우 화살표, Home/End) ----
  const tabs = [...app.querySelectorAll('[role="tab"]')];
  const show = t => { tabs.forEach(x => { const on = x === t; x.setAttribute("aria-selected", on); x.tabIndex = on ? 0 : -1; document.getElementById(x.getAttribute("aria-controls")).hidden = !on; }); t.focus(); };
  tabs.forEach((t, i) => { t.addEventListener("click", () => show(t));
    t.addEventListener("keydown", e => { const k = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key]; if (k != null) { e.preventDefault(); show(tabs[(k + tabs.length) % tabs.length]); } }); });
}
