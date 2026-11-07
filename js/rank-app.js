// PAY RANK 화면 컨트롤러(안티그래비티 pay-rank/js/app.js 의 구조를 PAY워치 디자인·데이터에 맞게 옮김).
// 흐름: 친구 추가 → 랭킹 만들기 → 공유. 기업 데이터는 처음 회사 입력창을 쓸 때(또는 공유 링크 복원 때) 불러온다.
import { chrome, esc, getJSON } from "./common.js?v=21f7cf11ea";
import { buildFinder, searchFinder, resultHref } from "./finder-core.js?v=21f7cf11ea";
import { loadEntities } from "./finder-ui.js?v=21f7cf11ea";
import { DISCLAIMER, MAX_FRIENDS, MIN_FRIENDS, MIX_NOTE, calculateRanking, companyRankInfo, formatSalary, makeCompanies, sourceLabel, topByIndustry } from "./rank-engine.js?v=21f7cf11ea";
import { copyToClipboard, downloadRankingImage, generateEmbedCode, generateShareUrl, nativeShare, parseShareParams } from "./rank-share.js?v=21f7cf11ea";

const params = parseShareParams(location.search);
if (params.embed) document.body.classList.add("rk-embed");
chrome("rank.html");
const $ = id => document.getElementById(id);
const state = { friends: [], next: 1, last: null, nickShare: false, basis: { c: "dart", i: "dart" } };
let DATA = null;

async function data() {
  if (DATA) return DATA;
  const [ents, rk] = await Promise.all([loadEntities(), getJSON("rank/rank.json")]);
  const companies = makeCompanies(ents, rk);
  DATA = { ents, rk, companies, byId: new Map(companies.map(c => [c.id, c])), inds: rk.inds };
  return DATA;
}
const payTag = c => (c.pay ? `<b>${esc(formatSalary(c.pay))}</b>` : "연봉 자료 없음");
const link = c => `<a href="${esc(resultHref({ code: c.id }))}">${esc(c.name)}</a>`;

// ---- 회사 자동완성(키보드 탐색·초성·동명 법인은 식별자로 구분) ----
function attach(input, list, onPick, onClear) {
  let act = -1, cur = [];
  const close = () => { list.hidden = true; act = -1; input.setAttribute("aria-expanded", "false"); };
  const mark = () => [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === act)));
  input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list"); input.setAttribute("aria-expanded", "false");
  input.addEventListener("input", async () => {
    onClear && onClear();
    const q = input.value.trim();
    if (!q) return close();
    const d = await data();
    if (input.value.trim() !== q) return;
    cur = searchFinder(d.ents, q, 7).results.map(e => d.byId.get(e.code)).filter(Boolean);
    list.innerHTML = cur.length ? cur.map((c, i) => `<li role="option" data-i="${i}" aria-selected="false"><span class="nm">${esc(c.name)}${c.name !== c.legal ? `<br><small>${esc(c.legal)}</small>` : ""}</span><span class="mt">${c.pay ? `${esc(formatSalary(c.pay))} · ${esc(sourceLabel(c.src))}` : "연봉 자료 없음"}</span></li>`).join("")
      : `<li class="em" role="option" aria-disabled="true">‘${esc(q)}’ 색인에서 찾지 못했습니다(회사가 없다는 뜻은 아닙니다).</li>`;
    list.hidden = false; act = -1; input.setAttribute("aria-expanded", "true");
  });
  input.addEventListener("keydown", e => {
    if (list.hidden || !cur.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); act = (act + 1) % cur.length; mark(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); act = (act - 1 + cur.length) % cur.length; mark(); }
    else if (e.key === "Enter") { e.preventDefault(); pick(act >= 0 ? act : 0); }
    else if (e.key === "Escape") close();
  });
  const pick = i => { const c = cur[i]; if (!c) return; input.value = c.name; close(); onPick(c); };
  list.addEventListener("mousedown", e => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); pick(+li.dataset.i); } });
  document.addEventListener("click", e => { if (!input.parentElement.contains(e.target)) close(); });
}

// ---- 친구들 랭킹 ----
function renderFriends() {
  const box = $("rk-friends");
  box.innerHTML = state.friends.map((f, i) => `<div class="rk-friend" data-id="${f.id}"><p class="no">친구 ${i + 1}</p>
    <input class="nick-in" type="text" maxlength="20" placeholder="별명" aria-label="친구 ${i + 1} 별명" value="${esc(f.nickname)}">
    <div class="rk-co"><input class="co-in" type="search" autocomplete="off" placeholder="회사 검색" aria-label="친구 ${i + 1} 회사" value="${f.company ? esc(f.company.name) : f.text || ""}"><ul class="rk-list" role="listbox" hidden></ul></div>
    <button type="button" class="rk-rm" aria-label="친구 ${i + 1} 삭제" ${state.friends.length <= MIN_FRIENDS ? "disabled" : ""}>×</button></div>`).join("");
  box.querySelectorAll(".rk-friend").forEach(row => {
    const f = state.friends.find(x => x.id === +row.dataset.id);
    row.querySelector(".nick-in").addEventListener("input", e => { f.nickname = e.target.value; });
    const ci = row.querySelector(".co-in");
    attach(ci, row.querySelector(".rk-list"), c => { f.company = c; f.text = ""; }, () => { f.company = null; f.text = ci.value; });
    ci.addEventListener("focus", data);
    row.querySelector(".rk-rm").addEventListener("click", () => { if (state.friends.length > MIN_FRIENDS) { state.friends = state.friends.filter(x => x !== f); renderFriends(); } });
  });
  $("btn-add").disabled = state.friends.length >= MAX_FRIENDS;
  $("btn-add").textContent = state.friends.length >= MAX_FRIENDS ? `친구는 최대 ${MAX_FRIENDS}명` : "+ 친구 추가";
}
const newFriend = (company = null, nickname = "") => ({ id: state.next++, nickname, company, text: "" });

function renderResult() {
  const r = calculateRanking(state.friends);
  state.last = r;
  const msg = $("rk-msg");
  if (!r.valid) { msg.textContent = r.message; return; }
  const missing = state.friends.filter(f => !f.company && f.text).length;
  msg.textContent = missing ? "목록에서 회사를 선택하지 않은 친구는 순위에서 제외했습니다(이름만 입력하면 다른 법인과 헷갈릴 수 있습니다)." : "";
  const box = $("rk-result");
  box.hidden = false;
  box.innerHTML = r.ranked.map(x => `<div class="rk-row ${x.rank <= 3 ? "top" : ""}"><div class="rank">${x.rank}위</div>
      <div class="who"><span class="nick">${esc(x.nickname)}</span><span class="co">${link({ id: x.companyId, name: x.companyName })}${x.tie ? " · 공동 순위" : ""}</span></div>
      <div class="pay">${esc(x.formatted)}<span class="src">${esc(x.source)}${x.year ? ` · ${x.year}년` : ""}</span></div></div>`).join("")
    + (r.unranked.length ? `<div class="rk-un"><h3>평균연봉 자료 없음(순위 제외)</h3><ul>${r.unranked.map(u => `<li>${esc(u.nickname)} — ${esc(u.companyName)} <span class="rk-tag">${esc(u.reason)}</span></li>`).join("")}</ul></div>` : "")
    + `<p class="rk-note"><b>${esc(DISCLAIMER)}</b>${r.mixedSources ? ` ${esc(MIX_NOTE)}` : ""}</p>`
    + (params.embed ? "" : `<div class="rk-share"><label><input type="checkbox" id="chk-nick"> 친구 별명도 링크·임베드에 포함(선택할 때만 주소에 들어갑니다)</label>
      <div class="grid"><button type="button" class="rk-btn primary" id="btn-png">이미지 저장(PNG)</button><button type="button" class="rk-btn" id="btn-copy">링크 복사</button>
      <button type="button" class="rk-btn" id="btn-share" hidden>공유하기</button><button type="button" class="rk-btn" id="btn-embed">임베드 코드</button></div>
      <div id="embed-box" hidden><textarea id="embed-code" readonly aria-label="임베드 코드"></textarea><button type="button" class="rk-btn" id="btn-embed-copy">임베드 코드 복사</button></div></div>`);
  if (!params.embed) bindShare();
  const url = generateShareUrl(state.friends, false);
  if (url.includes("?") && !params.embed) history.replaceState(null, "", url.slice(location.origin.length));      // 기업 식별자만(별명 없음), 임베드 화면은 주소를 바꾸지 않는다
}

const toast = t => { $("rk-msg").textContent = t; };
function bindShare() {
  const nick = () => !!$("chk-nick").checked, shareUrl = () => generateShareUrl(state.friends, nick());
  $("btn-png").addEventListener("click", async () => {
    const b = $("btn-png"); b.disabled = true; b.textContent = "이미지 만드는 중…";
    try { await downloadRankingImage(state.last, { pageUrl: generateShareUrl(state.friends, false), includeNickname: true }); toast("이미지를 저장했습니다. 이미지에는 별명이 들어 있으니 공유 전에 확인하세요."); }
    catch { toast("이미지를 만들지 못했습니다."); } finally { b.disabled = false; b.textContent = "이미지 저장(PNG)"; }
  });
  $("btn-copy").addEventListener("click", async () => toast((await copyToClipboard(shareUrl())) ? (nick() ? "별명이 포함된 링크를 복사했습니다." : "링크를 복사했습니다(별명 제외).") : "링크 복사에 실패했습니다."));
  if (navigator.share) { $("btn-share").hidden = false; $("btn-share").addEventListener("click", () => nativeShare("내 친구들 연봉 랭킹", "우리 중 누가 제일 잘 버는 회사에 다닐까?", shareUrl())); }
  $("btn-embed").addEventListener("click", () => { $("embed-code").value = generateEmbedCode(shareUrl()); $("embed-box").hidden = false; });
  $("btn-embed-copy").addEventListener("click", async () => toast((await copyToClipboard($("embed-code").value)) ? "임베드 코드를 복사했습니다." : "복사에 실패했습니다."));
}

// ---- 기업별 순위(보조) ----
function basisButtons(view, onChange) {
  const box = $(`view-${view === "c" ? "c" : "i"}`);
  box.querySelectorAll(".rk-basis button").forEach(b => b.addEventListener("click", () => {
    state.basis[view] = b.dataset.basis;
    box.querySelectorAll(".rk-basis button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    onChange();
  }));
}
let companyPick = null;
async function renderCompany() {
  const out = $("c-out"), c = companyPick;
  if (!c) { out.innerHTML = ""; return; }
  const d = await data(), basis = state.basis.c, info = companyRankInfo(d.companies, c, basis, c.ind >= 0 ? d.inds[c.ind] : null);
  const label = basis === "dart" ? "DART 공시 기준" : "사람인 추정 포함 통합 참고";
  out.innerHTML = `<div class="rk-card"><h2>${link(c)}${c.hold ? '<span class="rk-tag">지주회사</span>' : ""}</h2>
    <p class="rk-big">${c.pay ? esc(formatSalary(c.pay)) : "자료 없음"}</p>${c.pay ? `<p class="rk-note">${esc(sourceLabel(c.src))}${c.year ? ` · ${c.year}년` : ""}</p>` : ""}
    ${info && info.has ? `<div class="rk-ranks"><div><span>${esc(label)} · 비교 대상 ${info.total.toLocaleString("ko-KR")}곳 중</span><b>${info.rank.toLocaleString("ko-KR")}위</b></div>
      ${info.industry ? `<div><span>${esc(info.industry)} 업종 내 · 비교 대상 ${info.indTotal.toLocaleString("ko-KR")}곳 중</span><b>${info.indRank}위</b></div>` : `<div><span>업종 분류가 검증된 기업이 아니라 업종 내 순위를 만들지 않습니다.</span></div>`}</div>`
      : `<p class="rk-note">${esc(info ? info.reason : "")}</p>`}
    <p class="rk-note">${basis === "dart" ? "공시 평균급여가 있는 기업끼리만 비교합니다(사람인 추정 제외)." : esc(MIX_NOTE)} 개인 연봉이 아닌 회사 평균연봉 기준입니다.</p></div>`;
}

// ---- 업종별 순위(보조) ----
async function renderIndustry() {
  const d = await data(), sel = $("i-select"), basis = state.basis.i;
  if (!sel.options.length) {
    const counts = d.inds.map((_, i) => topByIndustry(d.companies, i, "dart", 0).total);
    sel.innerHTML = d.inds.map((n, i) => ({ n, i, k: counts[i] })).filter(x => x.k > 0).sort((a, b) => b.k - a.k).map(x => `<option value="${x.i}">${esc(x.n)}</option>`).join("");
  }
  const ind = +sel.value, { total, top } = topByIndustry(d.companies, ind, basis, 20);
  $("i-out").innerHTML = `<p class="rk-note">${esc(basis === "dart" ? "DART 공시 기준" : "사람인 추정 포함 통합 참고")} · 순위 산정 대상 <b>${total.toLocaleString("ko-KR")}곳</b>(업종 분류가 검증된 기업만) · 상위 20곳</p>`
    + (top.length ? `<table class="rk-tab"><thead><tr><th class="n">순위</th><th>기업</th><th class="n">평균연봉</th></tr></thead><tbody>${top.map(c => `<tr><td class="n"><b>${c.rank}</b></td><td>${link(c)}${c.hold ? '<span class="rk-tag">지주회사</span>' : ""}</td><td class="n"><b>${esc(formatSalary(c.pay))}</b><br><small>${esc(sourceLabel(c.src))}${c.year ? ` · ${c.year}년` : ""}</small></td></tr>`).join("")}</tbody></table>` : `<p class="rk-note">이 기준으로 순위를 낼 기업이 없습니다.</p>`)
    + `<p class="rk-note">업종은 DART 업종코드를 고용노동부 산업 중분류로 옮긴 분류가 있는 기업만 포함하며, 분류가 없는 기업은 임의로 분류하지 않습니다. 지주회사는 평균급여 비교가 어려워 표시했습니다. 개인 연봉이 아닌 회사 평균연봉 기준입니다.</p>`;
}

// ---- 탭·초기화 ----
function tabs() {
  const ids = ["f", "c", "i"];
  const show = id => ids.forEach(k => { const on = k === id; $(`tab-${k}`).setAttribute("aria-selected", String(on)); $(`tab-${k}`).tabIndex = on ? 0 : -1; $(`view-${k}`).hidden = !on; });
  ids.forEach(k => $(`tab-${k}`).addEventListener("click", () => { show(k); if (k === "i") renderIndustry(); }));
  $("tab-f").parentElement.addEventListener("keydown", e => { const i = ids.findIndex(k => $(`tab-${k}`) === document.activeElement); if (i < 0 || !["ArrowLeft", "ArrowRight"].includes(e.key)) return; const n = ids[(i + (e.key === "ArrowRight" ? 1 : -1) + 3) % 3]; show(n); $(`tab-${n}`).focus(); if (n === "i") renderIndustry(); });
}

(async function init() {
  tabs();
  state.friends = [newFriend(), newFriend()];
  $("btn-add").addEventListener("click", () => { if (state.friends.length < MAX_FRIENDS) { state.friends.push(newFriend()); renderFriends(); } });
  $("btn-make").addEventListener("click", async () => { await data(); renderResult(); });
  attach($("c-input"), $("c-list"), c => { companyPick = c; renderCompany(); }, () => {});
  $("c-input").addEventListener("focus", data);
  basisButtons("c", renderCompany); basisButtons("i", renderIndustry); $("i-select").addEventListener("change", renderIndustry);
  if (params.ids.length) {                                                       // 공유 링크 복원: 같은 기업 조합의 랭킹
    const d = await data();
    const fr = params.ids.map((id, i) => newFriend(d.byId.get(id) || null, params.nicks[i] || `친구 ${i + 1}`));
    while (fr.length < MIN_FRIENDS) fr.push(newFriend());
    state.friends = fr;
    renderFriends();
    renderResult();
    return;
  }
  if (params.add) {                                                              // 기업 상세의 '내 친구들 회사와 비교하기': 현재 기업이 첫 번째 친구로 등록
    const d = await data(), c = d.byId.get(params.add);
    if (c) state.friends[0].company = c;
  }
  renderFriends();
})();
