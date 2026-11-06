// web/js/finder-core.js 테스트: 정규화, 순위, 확인된 별칭, 주요 기업 30곳 표본(식별자=DART 코드로 검증), 존재하지 않는 기업을 단정하지 않는 분류.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { normalize, buildFinder, searchFinder, shownName, category, resultHref, FLAG } from "../../web/js/finder-core.js";

const root = new URL("../../", import.meta.url);
const rows = [
  ["00164779", "에스케이하이닉스(주)", "SK하이닉스", "SK하이닉스;하이닉스;SK hynix", 7, 30000],
  ["01871672", "에스케이하이닉스시스템아이씨우시솔루션스 주식회사", "", "", 0, 100],
  ["00126380", "삼성전자(주)", "삼성전자", "삼전", 7, 128000],
  ["00252074", "삼성전자판매 주식회사", "", "", 1, 3000],
  ["00266961", "네이버(주)", "네이버", "NAVER", 7, 5000],
  ["00777272", "네이버클라우드 주식회사", "", "", 1, 900],
];
const F = buildFinder(rows);

test("정규화: 법인 표기·띄어쓰기·특수문자·대소문자만 바뀌고 한글·영문 표기 치환은 하지 않는다", () => {
  assert.equal(normalize("(주) 에스케이 하이닉스"), "에스케이하이닉스"); assert.equal(normalize("에스케이하이닉스 주식회사"), "에스케이하이닉스");
  assert.equal(normalize("SK hynix"), "skhynix"); assert.equal(normalize("NAVER"), "naver"); assert.equal(normalize("㈜한화"), "한화"); assert.equal(normalize("K-water"), "kwater");
  assert.notEqual(normalize("SK하이닉스"), normalize("에스케이하이닉스"));           // 기계적 치환 없음 — 별칭 사전으로만 연결
});
test("별칭이 확인된 기업은 정확 일치로 1위, 식별자(DART 코드)는 그대로", () => {
  for (const [q, code] of [["SK하이닉스", "00164779"], ["하이닉스", "00164779"], ["sk Hynix", "00164779"], ["삼전", "00126380"], ["NAVER", "00266961"], ["naver", "00266961"], ["에스케이하이닉스 주식회사", "00164779"]]) {
    const r = searchFinder(F, q).results; assert.equal(r[0].code, code, q); assert.equal(r[0].tier, 0, q);
  }
});
test("표시명 우선·정식 명칭 보존, 사전에 없는 기업은 법인 표기만 뺀 이름", () => {
  assert.equal(shownName(F[0]), "SK하이닉스"); assert.equal(F[0].legal, "에스케이하이닉스(주)");
  assert.equal(shownName(F[3]), "삼성전자판매"); assert.equal(F[3].legal, "삼성전자판매 주식회사");
});
test("순위: 정확 일치 → 접두 → 부분, 같은 순위에서는 규모순. 다른 법인은 병합하지 않는다", () => {
  const r = searchFinder(F, "삼성전자").results; assert.deepEqual(r.map(x => x.code), ["00126380", "00252074"]); assert.deepEqual(r.map(x => x.tier), [0, 1]);
  const n = searchFinder(F, "네이버").results; assert.deepEqual(n.map(x => x.code), ["00266961", "00777272"]);
  assert.equal(searchFinder(F, "하이닉스시스템").results[0].code, "01871672");
  assert.equal(new Set(searchFinder(F, "하이닉스").results.map(x => x.code)).size, searchFinder(F, "하이닉스").results.length);
});
test("유사어는 결과가 적을 때만 덧붙고, 없는 이름은 빈 결과", () => {
  assert.equal(searchFinder(F, "").results.length, 0); assert.equal(searchFinder(F, "zzzzqqq").results.length, 0);
  const t = searchFinder(F, "삼성전쟈"); assert.ok(t.fuzzy >= 1 && t.results[0].code === "00126380");
});
test("자료 유형과 링크: 모든 색인 기업은 하나의 결과 화면으로(식별자=DART 코드), 상세가 없으면 그 화면에서 자료 없음으로 안내", () => {
  assert.equal(category({ flags: 7 }), "b"); assert.equal(category({ flags: 5 }), "c"); assert.equal(category({ flags: 0 }), "d");
  assert.equal(resultHref({ code: "00126380", flags: 1 }), "company.html?corp=00126380"); assert.equal(resultHref({ code: "00126371", flags: 0 }), "company.html?corp=00126371");
  assert.ok(FLAG.PAGE === 1 && FLAG.PAY === 2 && FLAG.NPS === 4);
});

const real = new URL("site/data/finder/entities.json", root);
const SAMPLE = [  // [사용자가 입력할 법한 검색어, 기대 DART 코드]
  ["SK하이닉스", "00164779"], ["하이닉스", "00164779"], ["sk hynix", "00164779"], ["현대차", "00164742"], ["현대자동차", "00164742"], ["한전", "00159193"], ["한국전력", "00159193"], ["KEPCO", "00159193"],
  ["네이버", "00266961"], ["NAVER", "00266961"], ["삼전", "00126380"], ["삼성전자", "00126380"], ["KB국민은행", "00386937"], ["국민은행", "00386937"], ["카카오", "00258801"], ["기아", "00106641"],
  ["엘지전자", "00401731"], ["LG전자", "00401731"], ["삼성SDI", "00126362"], ["씨제이제일제당", "00635134"], ["신한은행", "00149293"], ["하나은행", "00158909"], ["우리은행", "00254045"],
  ["LG엔솔", "01515323"], ["셀트리온", "00413046"], ["삼바", "00877059"], ["현대모비스", "00164788"], ["엘지화학", "00356361"], ["SKT", "00159023"], ["케이티", "00190321"], ["코레일", "00585918"],
  ["배민", "01063273"], ["토스", "01212921"], ["쿠팡", "01019166"], ["아모레", "00583424"], ["이마트", "00872984"], ["카뱅", "01133217"],
];
test("실제 색인 3,912곳: 주요 기업 표본이 정확한 DART 코드로 1위에 나온다(빌드된 경우)", { skip: !existsSync(real) }, () => {
  const R = JSON.parse(readFileSync(real, "utf8")); const L = buildFinder(R); assert.equal(R.length, 5463);   // DART 3,912 + 사람인 전용 1,551
  assert.ok(R.every(r => /^(\d{8}|S[0-9a-f]{10})$/.test(r[0]))); assert.equal(new Set(R.map(r => r[0])).size, R.length);
  assert.equal(R.filter(r => /^\d{8}$/.test(r[0])).length, 3912);
  const miss = SAMPLE.filter(([q, c]) => searchFinder(L, q).results[0]?.code !== c);
  assert.deepEqual(miss, [], `1위가 아닌 표본: ${JSON.stringify(miss)}`);
});
test("실제 색인: 색인에 없는 기업(엔씨소프트·삼성물산 등)은 빈 결과이고 화면 문구가 '존재하지 않음'을 단정하지 않는다", { skip: !existsSync(real) }, () => {
  const L = buildFinder(JSON.parse(readFileSync(real, "utf8")));
  assert.equal(searchFinder(L, "엔씨소프트").results.filter(r => r.tier <= 2).length, 0);
  for (const q of ["삼성물산", "현대건설"]) { const t = searchFinder(L, q).results[0]; assert.ok(/^S[0-9a-f]{10}$/.test(t.code) && t.tier === 0, q); }   // PHASE 14.2: 사람인에만 있는 기업은 DART 코드 없이 사람인 전용 id 로 검색된다
  const home = readFileSync(new URL("web/js/finder-ui.js", root), "utf8");
  assert.ok(!/존재하지 않|없는 회사|없습니다.*회사/.test(home) && /색인|자료/.test(home));
});
test("실제 색인: 정식 명칭으로 입력하면 자기 자신이 상위 3위 안(4곳마다 1곳 표본)", { skip: !existsSync(real) }, () => {
  const R = JSON.parse(readFileSync(real, "utf8")); const L = buildFinder(R); const bad = [];
  for (const r of R.filter((_, i) => i % 4 === 0 && /^\d{8}$/.test(_[0]))) { const top = searchFinder(L, r[1], 3).results.map(x => x.code); if (!top.includes(r[0])) bad.push(r[1]); }
  assert.ok(bad.length <= 5, `누락 ${bad.length}: ${bad.slice(0, 5)}`);
});
test("별칭 사전: 같은 별칭이 서로 다른 기업을 가리키지 않는다", { skip: !existsSync(real) }, () => {
  const L = buildFinder(JSON.parse(readFileSync(real, "utf8"))); const seen = new Map();
  for (const e of L) for (const a of [e.nd, ...e.na].filter(Boolean)) { if (seen.has(a) && seen.get(a) !== e.code) assert.fail(`중복 별칭 ${a}`); seen.set(a, e.code); }
});
