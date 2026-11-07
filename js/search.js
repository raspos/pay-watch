// 검색: ①첫 로드 top.json(가입자 100명 이상) ②앞 두 글자 청크(필요할 때만) ③Fuse 로 오타 허용. 서버 없음.
import { esc, fmtInt, getJSON, searchKey } from "./common.js?v=d822ce9827";

let topPromise = null;
export function loadTop() {
  if (!topPromise) topPromise = getJSON("index/top.json").then(rows => {
    const items = rows.map(r => toItem(r));
    const fuse = typeof window.Fuse === "function" ? new window.Fuse(items, { keys: ["sk"], threshold: 0.3, ignoreLocation: true, minMatchCharLength: 2 }) : null;
    return { items, fuse };
  });
  return topPromise;
}
const toItem = r => ({ id: r[0], name: r[1], ind: r[2], loc: r[3], subs: r[4], pay: !!r[5], indiv: !!r[6], sk: searchKey(r[1]) });

// 정렬된 검색 키를 연속 구간으로 나눈 청크(index/r/N.json)와 구간 시작 키 목록(index/ranges.json)
async function loadChunk(sk) {
  try {
    const starts = await getJSON("index/ranges.json");
    if (!starts.length) return [];
    const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);     // UTF-16 코드 단위 순(파이썬 쪽 정렬과 동일)
    let lo = 0, hi = starts.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (cmp(starts[mid], sk) <= 0) lo = mid; else hi = mid - 1; }
    const ids = [lo];
    for (let j = lo + 1; j < starts.length && starts[j].startsWith(sk) && ids.length < 6; j++) ids.push(j);
    const parts = await Promise.all(ids.map(i => getJSON(`index/r/${i}.json`)));
    return parts.flat().map(toItem);
  } catch { return []; }
}

// 널리 쓰는 통칭 → 사업장명(정규화 키). 전체 별칭 사전은 편집 과제(현재는 대표적인 몇 개만)
const ALIAS = { "케이비국민은행": "국민은행", "kb국민은행": "국민은행", "현대차": "현대자동차", "기아자동차": "기아", "엘지에너지솔루션": "엘지에너지솔루션" };
const keyOf = q => { const k = searchKey(q); return ALIAS[k] || k; };

function rank(items, fuse, sk, extra = []) {
  const seen = new Set(), out = [];
  const add = arr => arr.forEach(it => { if (!seen.has(it.id)) { seen.add(it.id); out.push(it); } });
  const bySubs = (a, b) => b.subs - a.subs;
  add(items.filter(it => it.sk.startsWith(sk)).sort(bySubs));
  add(extra.filter(it => it.sk.startsWith(sk)).sort(bySubs));
  add(items.filter(it => it.sk.includes(sk)).sort(bySubs));
  let fuzzy = 0;
  if (out.length < 6 && fuse && [...sk].length >= 3) {
    const before = out.length;
    add(fuse.search(sk, { limit: 8 }).map(r => r.item));
    fuzzy = out.length - before;
  }
  return { out, fuzzy };
}

// 1단계: top.json(가입자 100명 이상)만으로 즉시 결과. 2단계(search): 앞 두 글자 청크를 받아 작은 사업장까지 합침.
export async function searchTop(q, limit = 12) {
  const sk = keyOf(q);
  if (!sk) return { list: [], fuzzy: 0, more: false };
  const { items, fuse } = await loadTop();
  const { out, fuzzy } = rank(items, fuse, sk);
  return { list: out.slice(0, limit), fuzzy, more: [...sk].length >= 2 };
}

export async function search(q, limit = 12) {
  const sk = keyOf(q);
  if (!sk) return { list: [], fuzzy: 0 };
  const { items, fuse } = await loadTop();
  const extra = [...sk].length >= 2 ? await loadChunk(sk) : [];
  const { out, fuzzy } = rank(items, fuse, sk, extra);
  return { list: out.slice(0, limit), fuzzy };
}

// 같은 이름 구분용 표시: 업종, 소재지, 가입자 수
export function itemMeta(it) {
  return `${esc(it.ind)}, ${esc(it.loc)}, 가입자 ${fmtInt(it.subs)}명, ${it.pay ? "추정급여 제공" : "추정급여 비공개(10명 미만)"}`;
}

// ARIA combobox. onPick(item) 호출. 엔터 시 활성 항목 선택.
export function mountSearch(root, { onPick, placeholder = "회사명을 입력하세요 (예: 삼성전자)", label = "회사명 검색" } = {}) {
  const uid = "s" + Math.random().toString(36).slice(2, 7);
  root.innerHTML = `<label class="vh" for="${uid}i">${esc(label)}</label>
    <input id="${uid}i" type="search" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="false" aria-controls="${uid}l" aria-autocomplete="list" placeholder="${esc(placeholder)}">
    <ul class="results" id="${uid}l" role="listbox" aria-label="검색 결과" hidden></ul><div class="vh" role="status" aria-live="polite" id="${uid}s"></div>`;
  const input = root.querySelector("input"), list = root.querySelector("ul"), status = root.querySelector(`#${uid}s`);
  let cur = [], act = -1, seq = 0, timer = null;
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); act = -1; };
  const setAct = i => {
    act = i;
    [...list.children].forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
    if (i >= 0) { input.setAttribute("aria-activedescendant", `${uid}o${i}`); list.children[i].scrollIntoView({ block: "nearest" }); } else input.removeAttribute("aria-activedescendant");
  };
  const render = (res, q) => {
    cur = res.list;
    if (!cur.length) list.innerHTML = `<li class="empty" role="option" aria-disabled="true">‘${esc(q)}’ 검색 결과가 없습니다. 이름의 일부만 입력해 보세요.</li>`;
    else list.innerHTML = cur.map((it, i) => `<li id="${uid}o${i}" role="option" aria-selected="false" data-i="${i}"><div class="nm">${esc(it.name)}${it.indiv ? ' <span class="tag">개인사업장</span>' : ""}</div><div class="meta">${itemMeta(it)}</div></li>`).join("")
      + (res.fuzzy ? `<li class="empty" role="presentation">비슷한 이름 ${res.fuzzy}건 포함</li>` : "");
    list.hidden = false; input.setAttribute("aria-expanded", "true"); act = -1;
    status.textContent = cur.length ? `${cur.length}개 결과. 위아래 화살표로 이동, 엔터로 선택` : "결과 없음";
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { close(); return; }
    timer = setTimeout(async () => {
      const my = ++seq;
      const fast = await searchTop(q);                       // 즉시 표시
      if (my !== seq) return;
      if (fast.list.length || !fast.more) render(fast, q); else { list.innerHTML = `<li class="empty" role="option" aria-disabled="true">‘${esc(q)}’ 찾는 중…</li>`; list.hidden = false; input.setAttribute("aria-expanded", "true"); }
      if (fast.more) { const full = await search(q); if (my === seq) render(full, q); }   // 작은 사업장까지 합친 결과로 교체
    }, 90);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!list.hidden && cur.length) setAct((act + 1) % cur.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (!list.hidden && cur.length) setAct((act - 1 + cur.length) % cur.length); }
    else if (e.key === "Enter") {
      // close() 가 act 를 초기화하므로 선택 항목을 먼저 꺼낸다(순서가 바뀌면 undefined 가 전달되어 키보드로 선택할 수 없었다)
      const it = act >= 0 && cur[act] ? cur[act] : (cur.length && !list.hidden ? cur[0] : null);
      if (it) { e.preventDefault(); close(); onPick(it); }
    }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", e => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); close(); onPick(cur[+li.dataset.i]); } });
  document.addEventListener("click", e => { if (!root.contains(e.target)) close(); });
  return { input, close };
}
