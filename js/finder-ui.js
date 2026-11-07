// 통합 기업 찾기 입력창(ARIA combobox). DART 법인 색인(finder-core)과 국민연금 사업장 검색(search.js)을 한 입력창으로 합친다.
// 결과 항목은 식별자(DART 법인코드 또는 국민연금 사업장 id)를 그대로 들고 있으며, 선택하면 onPick(item) 만 호출한다.
import { esc, getJSON, searchKey } from "./common.js?v=1fc405ae56";
import { CATEGORY_LABEL, buildFinder, category, searchFinder, shownName } from "./finder-core.js?v=1fc405ae56";
import { normalize } from "./finder-core.js?v=1fc405ae56";

let entPromise = null;
export const loadEntities = () => (entPromise ||= getJSON("finder/entities.json").then(buildFinder));

const NOT_FOUND = "색인에서 찾지 못했습니다. 색인에 없는 이름일 뿐 회사가 없다는 뜻은 아닙니다. 이름의 일부만 입력해 보세요.";

/** options: onPick(item), placeholder, label, nps(async q => [{id,name,...}]|null: 국민연금 사업장 검색 함수), badge(entity) => 짧은 상태 문구 */
export function mountFinder(root, { onPick, placeholder = "회사 이름을 검색하세요", label = "회사 검색", nps = null, badge = null, autofocus = false } = {}) {
  const uid = "f" + Math.random().toString(36).slice(2, 7);
  root.innerHTML = `<label class="vh" for="${uid}i">${esc(label)}</label>
    <input id="${uid}i" type="search" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="search" inputmode="search" role="combobox" aria-expanded="false" aria-controls="${uid}l" aria-autocomplete="list" placeholder="${esc(placeholder)}">
    <ul class="results" id="${uid}l" role="listbox" aria-label="검색 결과" hidden></ul><div class="vh" role="status" aria-live="polite" id="${uid}s"></div>`;
  const input = root.querySelector("input"), list = root.querySelector("ul"), status = root.querySelector(`#${uid}s`);
  let cur = [], act = -1, seq = 0, timer = null, dirty = false;      // dirty: 입력 후 아직 결과가 갱신되지 않음
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); act = -1; };
  const setAct = i => {
    act = i; [...list.querySelectorAll("li[data-i]")].forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
    const li = list.querySelector(`li[data-i="${i}"]`);
    if (li) { input.setAttribute("aria-activedescendant", li.id); li.scrollIntoView({ block: "nearest" }); } else input.removeAttribute("aria-activedescendant");
  };
  const catText = e => (badge ? badge(e) : (typeof window.__pwBadge === "function" ? window.__pwBadge(e) : CATEGORY_LABEL[category(e)]));   // __pwBadge: 연구용 미리보기만 정의
  const render = (ents, wps, q) => {
    cur = [...ents.map(e => ({ kind: "corp", e })), ...wps.map(w => ({ kind: "wp", w }))];
    let i = 0, html = "";
    const rowHtml = it => {
      const id = `${uid}o${i}`;
      if (it.kind === "corp") {
        const e = it.e, name = shownName(e), sub = [name !== e.legal ? e.legal : null, catText(e)].filter(Boolean).join(" · ");
        return `<li id="${id}" role="option" aria-selected="false" data-i="${i++}"><div class="nm">${esc(name)}</div><div class="meta">${esc(sub)}</div></li>`;
      }
      const w = it.w; return `<li id="${id}" role="option" aria-selected="false" data-i="${i++}"><div class="nm">${esc(w.name)}</div><div class="meta">${esc([w.ind, w.loc].filter(Boolean).join(", "))}</div></li>`;
    };
    if (ents.length) html += cur.filter(c => c.kind === "corp").map(rowHtml).join("");
    if (wps.length) html += `<li class="grp" role="presentation">국민연금 사업장</li>` + cur.filter(c => c.kind === "wp").map(rowHtml).join("");
    if (!cur.length) html = `<li class="empty" role="option" aria-disabled="true">‘${esc(q)}’ ${NOT_FOUND}</li>`;
    list.innerHTML = html; list.hidden = false; input.setAttribute("aria-expanded", "true"); act = -1;
    status.textContent = cur.length ? `${cur.length}개 결과. 위아래 화살표로 이동, 엔터로 선택` : "결과 없음";
  };
  const run = async () => {
    const q = input.value.trim(); const my = ++seq; dirty = false;
    if (!q) { close(); return; }
    const ents = await loadEntities(); if (my !== seq) return;
    const { results } = searchFinder(ents, q, 6);
    render(results, [], q);
    if (nps) {                                                          // 국민연금 사업장은 느릴 수 있으므로 법인 결과를 먼저 보이고 이어서 합친다
      const seen = new Set(results.map(e => normalize(e.legal)));
      const k = searchKey(q);                                              // 국민연금 사업장은 이름이 검색어로 '시작'하는 것만(공사 현장·일용 등 이름 속 부분 일치는 오해를 부른다)
      const wps = ((await nps(q)) || []).filter(w => w.sk && w.sk.startsWith(k) && !seen.has(normalize(w.name))).slice(0, 4);
      if (my === seq && wps.length) render(results, wps, q);
    }
  };
  const pickAt = i => { const it = cur[i]; if (!it) return; close(); input.blur(); onPick(it); };
  input.addEventListener("input", () => { dirty = true; clearTimeout(timer); timer = setTimeout(run, 80); });
  input.addEventListener("focus", () => { loadEntities(); if (input.value.trim()) run(); });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!list.hidden && cur.length) setAct((act + 1) % cur.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (!list.hidden && cur.length) setAct((act - 1 + cur.length) % cur.length); }
    else if (e.key === "Enter") {
      if (dirty && input.value.trim()) { e.preventDefault(); clearTimeout(timer); run().then(() => { if (cur.length) pickAt(0); }); return; }   // 결과가 뜨기 전에 엔터를 눌러도 최신 입력의 1순위를 선택
      const i = act >= 0 ? act : (cur.length && !list.hidden ? 0 : -1); if (i >= 0) { e.preventDefault(); pickAt(i); }
    }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", e => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); pickAt(+li.dataset.i); } });
  document.addEventListener("click", e => { if (!root.contains(e.target)) close(); });
  if (autofocus) input.focus();
  return { input, close, setValue: v => { input.value = v; } };
}
