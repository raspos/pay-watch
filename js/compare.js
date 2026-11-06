import { avatar, chrome, esc, getDetail, getJSON, getMeta } from "./common.js?v=fc247f737b";
import { getCorp } from "./corp.js?v=fc247f737b";
import { searchTop } from "./search.js?v=fc247f737b";
import { loadEntities, mountFinder } from "./finder-ui.js?v=fc247f737b";
import { getSaramin } from "./saramin.js?v=fc247f737b";
import { MAX_ITEMS, MIN_ITEMS, evaluateAll, fmtValue, fromCorp, fromEntity, fromWorkplace, parseItems, toQuery } from "./compare-core.js?v=fc247f737b";

chrome("compare.html");
const out = document.getElementById("out"), picks = document.getElementById("picks"), addwrap = document.getElementById("addwrap");
let meta, ents = [];

// 키(c회사/w사업장) → 비교 대상. 회사의 대표 사업장은 회사 단위로 올려 비교한다(공시 값 포함).
async function resolve(key) {
  const id = key.slice(1);
  if (key[0] === "s") {                                                  // 사람인에만 있는 기업
    const pid = "S" + id, e = (await loadEntities()).find(x => x.code === pid);
    return e ? fromEntity(e, { saramin: await getSaramin(pid) }) : null;
  }
  if (key[0] === "c") {
    const c = await getCorp(id);
    const sm = await getSaramin(id);
    if (c) { c.saramin = sm; return fromCorp(c); }
    const e = (await loadEntities()).find(x => x.code === id);           // 상세 자료가 없는 기업도 비교에 넣고 가진 값만 표시
    const only = await getJSON("finder/dart_only.json").catch(() => ({}));
    return e ? fromEntity(e, { dart: only[id] || null, saramin: sm }) : null;
  }
  const d = await getDetail(id, meta.n_shards);
  if (!d) return null;
  if (d.co && d.co.p) { const c = await getCorp(d.co.c); if (c) return fromCorp(c); }
  return fromWorkplace(d);
}

async function add(key) {
  if (ents.length >= MAX_ITEMS) return;
  const e = await resolve(key);
  if (!e || ents.some(x => x.key === e.key)) return;
  ents.push(e);
  sync();
}
function remove(i) { ents.splice(i, 1); sync(); }
function sync() { history.replaceState(null, "", location.pathname + toQuery(ents.map(e => e.key))); render(); }

mountFinder(document.getElementById("add"), { label: "비교할 회사 검색", placeholder: "회사를 검색해 추가하세요", nps: async q => (await searchTop(q, 6)).list,
  onPick: it => add(it.kind === "wp" ? `w${it.w.id}` : /^\d{8}$/.test(it.e.code) ? `c${it.e.code}` : `s${it.e.code.slice(1)}`) });

function render() {
  picks.innerHTML = ents.map((e, i) => `<li class="pick">${avatar(e.name)}<div class="pn"><a href="${esc(e.href)}">${esc(e.name)}</a><small>${e.noData ? "자료 없음" : /^s/.test(e.key) ? "사람인 기준 기업" : e.kind === "corp" ? "회사(법인)" : "사업장 단독"}</small></div><button type="button" data-i="${i}" aria-label="${esc(e.name)} 비교에서 빼기">빼기</button></li>`).join("");
  picks.querySelectorAll("button").forEach(b => b.addEventListener("click", () => remove(+b.dataset.i)));
  addwrap.hidden = ents.length >= MAX_ITEMS;
  document.getElementById("addlab").textContent = `회사 추가 (현재 ${ents.length}곳, 최대 ${MAX_ITEMS}곳)`;
  if (ents.length < MIN_ITEMS) { out.innerHTML = ""; presets(); return; }

  const all = evaluateAll(ents);
  // 값이 아무에게도 없는 '순위 비교 없음' 항목(동종업계 위치)은 잡음이므로 제외한다
  const rows = all.rows.filter(({ row, res }) => !(row.noBars && res.present.length === 0)), comparableRows = all.comparableRows;
  const names = ents.map(e => esc(e.name)).join(' <span class="vs" aria-label="대">VS</span> ');
  out.innerHTML = `<h2 class="vsline">${names}</h2>
    <p class="disclaimer">같은 기준으로 우열을 표시한 항목 ${comparableRows}개, 기준이 달라 표시하지 않은 항목 ${rows.length - comparableRows}개.</p>
    ${rows.filter(x => x.row.primary).map(({ row, res }) => section(row, res)).join("")}
    ${sourceLine()}
    ${rows.some(x => !x.row.primary) ? `<details class="more"><summary>국민연금 기반 지표 더 보기</summary>${rows.filter(x => !x.row.primary).map(({ row, res }) => section(row, res)).join("")}</details>` : ""}
    <p class="disclaimer">국민연금 고지액 기반 추정치이며 실제 연봉과 다를 수 있습니다. 공시 급여는 DART 직원현황에서 계산한 값입니다. 회사 평균이며 개인의 실제 연봉이 아닙니다.</p>`;
}

// 대표 평균연봉의 출처·기준연도: 회사마다 따로 적고, 사업연도가 다르면 알린다. 값이 없으면 이유를 적는다.
function sourceLine() {
  const items = ents.map(e => `${esc(e.name)}: ${e.dart && e.dart.level === "ok" ? `DART 공시 ${esc(e.dart.fy)}년` : e.hold ? "공시 자료 확인 중" : e.dart ? "공시 일관성 미확인" : "공시 없음"}${e.saramin ? ` · 사람인 추정 표시연도 ${esc(e.saramin.fy)}년` : ""}`);
  const years = new Set(ents.filter(e => e.dart && e.dart.level === "ok").map(e => e.dart.fy));
  return `<p class="disclaimer">출처·기준연도 — ${items.join(" · ")}${years.size > 1 ? ". 사업연도가 서로 달라 직접 비교에 주의하세요." : ""}</p>`;
}

function section(row, res) {
  const tagCls = row.tag.startsWith("공시") ? "rep" : row.tag === "추정" ? "est" : "";
  const lines = ents.map((e, i) => {
    const v = res.values[i], lead = res.leaders.includes(i), capped = res.capped.includes(i);
    let bar = "";
    if (!row.noBars && v !== null) {
      if (res.signed) { const w = res.maxAbs ? Math.abs(v) / res.maxAbs * 50 : 0; bar = v >= 0 ? `<i style="left:50%;width:${w.toFixed(1)}%"></i>` : `<i style="right:50%;width:${w.toFixed(1)}%"></i>`; }
      else { const w = res.max ? Math.max(0, v) / res.max * 100 : 0; bar = `<i style="width:${w.toFixed(1)}%"></i>`; }
    }
    return `<div class="bl ${lead ? "lead" : ""} ${v === null ? "none" : ""}" role="listitem"><span class="bn">${esc(e.name)}</span>
      ${row.noBars ? "" : `<span class="bt ${res.signed ? "signed" : ""}" aria-hidden="true">${bar}</span>`}
      <span class="bv">${esc(fmtValue(row, v))}${lead ? ' <b class="lab">가장 높음</b>' : ""}${capped ? ' <span class="tag warn">상한 접근</span>' : ""}</span></div>`;
  }).join("");
  return `<section class="card battle" aria-labelledby="r-${row.id}"><h2 id="r-${row.id}">${esc(row.title)} <span class="tag ${tagCls}">${esc(row.tag)}</span></h2>
    <p class="disclaimer">${esc(row.basis)}</p><div class="bars ${row.noBars ? "plain" : ""}" role="list">${lines}</div>
    ${res.reason ? `<p class="reason" role="note">${esc(res.reason)}</p>` : ""}</section>`;
}

// 비교 대상이 2곳 미만일 때: 안내와 추천 대결(DART 법인코드로 고정)
const PAIRS = [["00126380", "삼성전자", "00164779", "SK하이닉스"], ["00164742", "현대자동차", "00106641", "기아"], ["00266961", "네이버", "00258801", "카카오"], ["00386937", "KB국민은행", "00149293", "신한은행"]];
function presets() {
  out.innerHTML = `<div class="empty-state">${ents.length ? "한 곳 더 추가하면 비교가 시작됩니다." : "비교할 회사를 2곳 이상 추가하세요."}</div>
    <section style="margin-top:12px"><h2 class="res-h">이런 비교는 어때요?</h2>${PAIRS.map(([a, an, b, bn]) => `<div class="rivalrow"><a href="compare.html?items=c${a},c${b}">${esc(an)}</a><span class="vs" aria-label="대">VS</span><a href="compare.html?items=c${a},c${b}">${esc(bn)}</a></div>`).join("")}</section>`;
}

(async () => {
  meta = await getMeta();
  const r = await Promise.all(parseItems(location.search).map(resolve));
  const seen = new Set();
  ents = r.filter(e => e && !seen.has(e.key) && seen.add(e.key));
  history.replaceState(null, "", location.pathname + toQuery(ents.map(e => e.key)));   // 예전 링크(a=,b=)는 새 형식으로
  render();
})().catch(e => { out.innerHTML = `<div class="empty-state">자료를 불러오지 못했습니다: ${esc(e.message)}</div>`; });
