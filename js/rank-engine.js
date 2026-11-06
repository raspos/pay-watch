// PAY RANK 계산 엔진(순수 로직, DOM 없음). 안티그래비티의 pay-rank/js/ranking.js 를 ES 모듈로 옮기고, 공개 데이터(rank/rank.json) 규격과 기업별·업종별 순위 계산을 더했다.
// 회사 객체(company): { id, name, legal, pay(원)|null, src(0=DART 공시, 1=사람인 추정)|null, year|null, ind(업종 번호, -1=분류 없음), hold(지주회사 표시) }
// 순위는 항상 '재직 회사의 평균연봉' 기준이며 개인 연봉이 아니다. 근속별 추정치는 쓰지 않는다. 같은 금액은 공동 순위(1224)로 처리한다.
export const DISCLAIMER = "친구 개인의 연봉이 아닌 재직 회사의 평균연봉 기준입니다.";
export const MIX_NOTE = "DART 공시와 사람인 추정은 산정 방식이 달라 직접 비교에 한계가 있습니다.";
export const MAX_FRIENDS = 10, MIN_FRIENDS = 2;
export const SOURCE_LABEL = ["DART 공시", "사람인 추정"];
export const sourceLabel = src => SOURCE_LABEL[src] ?? "자료 없음";

/** 금액(원) → "1억 3,700만원" / "9,800만원" */
export function formatSalary(amount) {
  if (typeof amount !== "number" || !Number.isFinite(amount) || amount <= 0) return "자료 없음";
  const man = Math.round(amount / 10000), uk = Math.floor(man / 10000), rest = man % 10000;
  if (uk > 0) return rest === 0 ? `${uk}억원` : `${uk}억 ${rest.toLocaleString("ko-KR")}만원`;
  return `${man.toLocaleString("ko-KR")}만원`;
}

const hasPay = c => !!c && typeof c.pay === "number" && c.pay > 0;

/** 친구 목록(2~10명)의 랭킹. friends: [{nickname, company}]. 같은 회사에 다니는 친구 여러 명도 각각 순위에 들어간다. */
export function calculateRanking(friends) {
  const empty = { ranked: [], unranked: [], mixedSources: false, years: [], disclaimer: DISCLAIMER };
  if (!Array.isArray(friends) || friends.length < MIN_FRIENDS) return { valid: false, message: `친구를 ${MIN_FRIENDS}명 이상 등록해 주세요.`, ...empty };
  if (friends.length > MAX_FRIENDS) return { valid: false, message: `친구는 최대 ${MAX_FRIENDS}명까지 등록할 수 있습니다.`, ...empty };
  const valid = [], unranked = [];
  friends.forEach((f, i) => {
    const nickname = String(f.nickname || "").trim() || `친구 ${i + 1}`, c = f.company;
    if (!c) { unranked.push({ nickname, companyId: null, companyName: "회사를 선택하지 않음", reason: "회사 미선택" }); return; }
    if (!hasPay(c)) { unranked.push({ nickname, companyId: c.id, companyName: c.name, reason: "평균연봉 자료 없음(순위에서 제외)" }); return; }
    valid.push({ nickname, companyId: c.id, companyName: c.name, legalName: c.legal, pay: c.pay, formatted: formatSalary(c.pay), src: c.src, source: sourceLabel(c.src), year: c.year, order: i });
  });
  valid.sort((a, b) => b.pay - a.pay || a.order - b.order);
  valid.forEach((v, i) => { v.rank = i > 0 && v.pay === valid[i - 1].pay ? valid[i - 1].rank : i + 1; v.tie = (i > 0 && v.pay === valid[i - 1].pay) || (i + 1 < valid.length && v.pay === valid[i + 1].pay); });
  const srcs = new Set(valid.map(v => v.src));
  return { valid: true, message: "", ranked: valid, unranked, mixedSources: srcs.size > 1, years: [...new Set(valid.map(v => v.year).filter(Boolean))].sort(), disclaimer: DISCLAIMER };
}

// ---- 기업별·업종별 순위(rank.json 의 행 배열 기준). basis: "dart"=DART 공시만(기본, 비교 가능한 값), "all"=사람인 추정을 포함한 통합 참고 순위 ----
const inBasis = (c, basis) => hasPay(c) && (basis === "all" || c.src === 0);
export function competitionRank(list, pay) { return list.reduce((n, c) => n + (c.pay > pay ? 1 : 0), 0) + 1; }

export function companyRankInfo(companies, company, basis = "dart", indName = null) {
  if (!company) return null;
  if (!hasPay(company)) return { has: false, reason: "평균연봉 자료가 없는 기업입니다. 순위를 만들지 않습니다." };
  if (!inBasis(company, basis)) return { has: false, reason: "DART 공시 평균연봉이 없어 DART 기준 순위가 없습니다. 통합 참고 순위(사람인 추정 포함)에서 확인하세요." };
  const all = companies.filter(c => inBasis(c, basis));
  const sameInd = company.ind >= 0 ? all.filter(c => c.ind === company.ind) : [];
  return { has: true, basis, rank: competitionRank(all, company.pay), total: all.length,
    industry: company.ind >= 0 ? indName : null, indRank: company.ind >= 0 ? competitionRank(sameInd, company.pay) : null, indTotal: sameInd.length };
}

export function topByIndustry(companies, ind, basis = "dart", n = 20) {
  const list = companies.filter(c => c.ind === ind && inBasis(c, basis)).sort((a, b) => b.pay - a.pay || (a.id < b.id ? -1 : 1));
  return { total: list.length, top: list.slice(0, n).map(c => ({ ...c, rank: competitionRank(list, c.pay) })) };
}

/** rank.json + 검색 색인 → 회사 객체들. entities: finder-core.buildFinder 결과, rk: {inds, rows} */
export function makeCompanies(entities, rk) {
  const pay = new Map(rk.rows.map(r => [r[0], r]));
  return entities.map(e => {
    const r = pay.get(e.code);
    return { id: e.code, name: e.display || String(e.legal).replace(/\(주\)|주식회사|㈜|\(유\)|유한회사/g, "").replace(/\s+/g, " ").trim() || e.legal, legal: e.legal, e,
      pay: r ? r[2] : null, src: r ? r[3] : null, year: r ? r[4] : null, ind: r ? r[5] : -1, hold: r ? r[6] : 0 };
  });
}
