// 통합 기업 찾기 엔진(순수 로직, A·B그룹 공통). 입력은 build_finder.py 가 만든 색인 행
// [dart_code, legal_name, display_name, aliases(;구분), flags, size]. 식별자(dart_code)는 어떤 경우에도 바꾸지 않는다.
// 순위: ① 별칭·표시명·정식 명칭과 정확히 일치 → ② 접두 일치 → ③ 부분 일치 → ④ 유사어(글자 쌍 겹침). 같은 순위에서는 규모(size)가 큰 기업 먼저.
// 법인 표기(주식회사·(주)·㈜ 등)·띄어쓰기·특수문자·영문 대소문자는 '검색 키를 만들 때만' 정규화하고 원본 이름은 보존한다.
// SK/에스케이 같은 한글·영문 표기는 기계적으로 치환하지 않고, 확인된 별칭 사전(config/search_aliases.csv)에 있는 항목만 처리한다.

export const FLAG = { PAGE: 1, PAY: 2, NPS: 4, SM: 8, SMONLY: 16 };   // SM: 사람인 평균연봉 있음, SMONLY: 사람인에만 있는 기업(DART 코드 없음)

const MARKS = /주식회사|유한회사|유한책임회사|합자회사|합명회사|㈜|㈔|\(주\)|\(유\)|\(사\)|\(합\)/g;

export function normalize(s) {
  return String(s ?? "").normalize("NFKC").toLowerCase().replace(MARKS, "").replace(/[^0-9a-zㄱ-ㆎ가-힣]/g, "");
}

const CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
/** 한글 초성 추출(한글 음절만 초성으로 바꾸고 나머지는 그대로). 초성 검색('ㅅㅅ' → 삼성)에 쓴다. */
export function chosung(s) {
  let o = "";
  for (const ch of String(s ?? "")) { const c = ch.charCodeAt(0) - 0xac00; o += c >= 0 && c <= 11171 ? CHO[Math.floor(c / 588)] : ch; }
  return o;
}
const JAMO_ONLY = /^[ㄱ-ㅎ]+$/;

export function buildFinder(rows) {
  return rows.map(r => {
    const aliases = r[3] ? r[3].split(";").filter(Boolean) : [];
    const display = r[2] || "";
    return { code: r[0], legal: r[1], display, aliases, flags: r[4], size: r[5] || 0,
      nl: normalize(r[1]), nd: normalize(display), na: aliases.map(normalize).filter(Boolean), cl: chosung(normalize(r[1])), cd: chosung(normalize(display)) };
  });
}

// 표시명: 사전에 확인된 표시명이 있으면 그것, 없으면 법인 표기만 뺀 이름(원본은 legal 에 보존)
export function shownName(e) { return e.display || String(e.legal).replace(MARKS, "").replace(/\s+/g, " ").trim() || e.legal; }

function bigrams(s) { const out = new Map(); const a = [...s]; for (let i = 0; i < a.length - 1; i++) { const g = a[i] + a[i + 1]; out.set(g, (out.get(g) || 0) + 1); } return out; }
function dice(a, b) {
  const A = bigrams(a), B = bigrams(b); let inter = 0, na = 0, nb = 0;
  A.forEach(v => { na += v; }); B.forEach(v => { nb += v; });
  A.forEach((v, k) => { inter += Math.min(v, B.get(k) || 0); });
  return na + nb ? (2 * inter) / (na + nb) : 0;
}

function tierOf(e, q) {
  const keys = [e.nl, e.nd, ...e.na].filter(Boolean);
  if (keys.some(k => k === q)) return 0;
  if (keys.some(k => k.startsWith(q))) return 1;
  if (keys.some(k => k.includes(q))) return 2;
  return 9;
}

export function searchFinder(list, query, limit = 8) {
  const raw = String(query ?? "").replace(/\s+/g, "");
  const q = JAMO_ONLY.test(raw) ? raw : normalize(query);                    // 초성은 NFKC 정규화가 호환 자모를 바꿔 버리므로 정규화 전에 판별
  if (!q) return { results: [], fuzzy: 0 };
  if (JAMO_ONLY.test(q)) {                                                    // 초성 검색: 표시명·정식 명칭의 초성 접두 → 부분 일치, 같은 순위에서는 규모순
    const hits = [];
    for (const e of list) { const keys = [e.cd, e.cl].filter(Boolean); const t = keys.some(k => k.startsWith(q)) ? 1 : keys.some(k => k.includes(q)) ? 2 : 9; if (t < 9) hits.push([t, e]); }
    hits.sort((a, b) => a[0] - b[0] || b[1].size - a[1].size || (a[1].code < b[1].code ? -1 : 1));
    return { results: hits.slice(0, limit).map(h => ({ ...h[1], tier: h[0] })), fuzzy: 0 };
  }
  const hits = [];
  for (const e of list) { const t = tierOf(e, q); if (t < 9) hits.push([t, e]); }
  hits.sort((a, b) => a[0] - b[0] || b[1].size - a[1].size || (a[1].code < b[1].code ? -1 : 1));
  let results = hits.slice(0, limit).map(h => ({ ...h[1], tier: h[0] }));
  let fuzzy = 0;
  if (results.length < Math.min(limit, 4) && [...q].length >= 3) {          // 결과가 적을 때만 유사어(오타) 보강
    const seen = new Set(results.map(r => r.code)); const cand = [];
    for (const e of list) {
      if (seen.has(e.code)) continue;
      let best = 0; for (const k of [e.nl, e.nd, ...e.na]) if (k) best = Math.max(best, dice(q, k));
      if (best >= 0.6) cand.push([best, e]);
    }
    cand.sort((a, b) => b[0] - a[0] || b[1].size - a[1].size);
    for (const [, e] of cand.slice(0, limit - results.length)) { results.push({ ...e, tier: 3 }); fuzzy++; }
  }
  return { results, fuzzy };
}

// 자료 유형(공개 화면): b=공시 평균급여, c=국민연금 정보만, d=검색은 되지만 급여 자료 부족. 'a'(공시+연구용 추정)는 연구용 미리보기에서만 겹쳐 붙인다.
export function category(e) {
  if (e.flags & FLAG.PAY) return "b";
  if (e.flags & FLAG.SM) return "e";
  if (e.flags & FLAG.NPS) return "c";
  return "d";
}
export const CATEGORY_LABEL = { a: "공시 급여 + 연구용 추정", b: "공시 평균급여", c: "국민연금 기반 정보", d: "급여 자료 부족", e: "사람인 추정 평균연봉" };

// 모든 색인 기업은 하나의 결과 화면으로 간다(상세 자료가 없으면 그 화면에서 '자료 없음'으로 안내). 식별자는 DART 법인코드 그대로.
export const resultHref = e => (/^\d{8}$/.test(e.code) ? `company.html?corp=${e.code}` : `company.html?sm=${e.code}`);   // DART 법인코드(8자리) 또는 사람인 전용 공개 id
