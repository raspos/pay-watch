// PAY RANK 순수 로직 테스트: 순위·공동 순위·급여 없는 기업·같은 회사 친구·DART/사람인 구분·기업별/업종별 순위·공유 링크(별명 보호, 하위 경로)·이미지 글자 줄바꿈·초성 검색.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { DISCLAIMER, MIX_NOTE, calculateRanking, companyRankInfo, formatSalary, makeCompanies, sourceLabel, topByIndustry } from "../../web/js/rank-engine.js";
import { ID_RE, generateEmbedCode, generateShareUrl, parseShareParams, sourceLine, wrapLines } from "../../web/js/rank-share.js";
import { buildFinder, searchFinder, chosung } from "../../web/js/finder-core.js";

const C = (id, name, pay, src = 0, year = 2025, ind = 1) => ({ id, name, legal: name, pay, src: pay ? src : null, year: pay ? year : null, ind, hold: 0 });
const A = C("00126380", "삼성전자", 153628246), B = C("00164779", "SK하이닉스", 120000000), S = C("S0123456789", "사람인기업", 99000000, 1), N = C("00999999", "자료없음", null);
const F = (nick, company) => ({ nickname: nick, company });

test("금액 표기", () => {
  assert.equal(formatSalary(153628246), "1억 5,363만원"); assert.equal(formatSalary(98000000), "9,800만원"); assert.equal(formatSalary(200000000), "2억원"); assert.equal(formatSalary(null), "자료 없음"); assert.equal(formatSalary(0), "자료 없음");
});
test("친구 2~10명 등록 범위", () => {
  assert.equal(calculateRanking([F("a", A)]).valid, false); assert.equal(calculateRanking(Array.from({ length: 11 }, (_, i) => F(`f${i}`, A))).valid, false);
  assert.equal(calculateRanking([F("a", A), F("b", B)]).valid, true); assert.equal(calculateRanking(Array.from({ length: 10 }, (_, i) => F(`f${i}`, A))).ranked.length, 10);
});
test("높은 연봉부터 정렬, 공동 순위(1,1,3), 같은 회사에 다니는 친구도 각각 순위", () => {
  const r = calculateRanking([F("가", B), F("나", A), F("다", A), F("라", S)]);
  assert.deepEqual(r.ranked.map(x => [x.nickname, x.rank]), [["나", 1], ["다", 1], ["가", 3], ["라", 4]]);        // 같은 금액은 공동 1위 다음이 3위
  assert.ok(r.ranked[0].tie && r.ranked[1].tie && !r.ranked[2].tie);
});
test("급여 없는 기업·회사 미선택은 순위를 만들지 않고 따로 표시", () => {
  const r = calculateRanking([F("가", A), F("나", N), F("다", null), F("라", B)]);
  assert.deepEqual(r.ranked.map(x => x.nickname), ["가", "라"]); assert.equal(r.unranked.length, 2);
  assert.ok(r.unranked.every(u => u.reason) && r.ranked.every(x => x.pay > 0));
});
test("DART 공시와 사람인 추정을 구분하고, 섞이면 산정 방식이 다르다고 표시", () => {
  const r = calculateRanking([F("가", A), F("나", S)]);
  assert.deepEqual(r.ranked.map(x => x.source), ["DART 공시", "사람인 추정"]); assert.equal(r.mixedSources, true); assert.match(MIX_NOTE, /산정 방식이 달라/);
  assert.equal(calculateRanking([F("가", A), F("나", B)]).mixedSources, false); assert.equal(sourceLabel(0), "DART 공시"); assert.equal(sourceLabel(1), "사람인 추정");
  assert.match(sourceLine(r), /DART 사업보고서 공시.*사람인 추정\(공시값 아님\)/);
  assert.equal(DISCLAIMER, "친구 개인의 연봉이 아닌 재직 회사의 평균연봉 기준입니다.");
});
test("공유 링크: 기업 식별자만, 별명은 명시적 선택 시에만, GitHub Pages 하위 경로 반영, 복원", () => {
  const loc = { origin: "https://raspos.github.io", pathname: "/pay-watch/rank.html" }, fr = [F("삼전맨", A), F("비밀친구", S)];
  const u = generateShareUrl(fr, false, loc); assert.equal(u, "https://raspos.github.io/pay-watch/rank.html?c=00126380,S0123456789"); assert.ok(!u.includes("%") && !u.includes("삼전맨") && !u.includes("n="));
  const un = generateShareUrl(fr, true, loc); assert.match(un, /&n=%EC%82%BC%EC%A0%84%EB%A7%A8,%EB%B9%84%EB%B0%80%EC%B9%9C%EA%B5%AC$/);
  const p = parseShareParams(new URL(un).search); assert.deepEqual(p.ids, ["00126380", "S0123456789"]); assert.deepEqual(p.nicks, ["삼전맨", "비밀친구"]);
  assert.deepEqual(parseShareParams("?c=00126380,bad,<script>,S0123456789&embed=1"), { ids: ["00126380", "S0123456789"], nicks: [], embed: true, add: null });
  assert.equal(parseShareParams("?add=00126380").add, "00126380"); assert.equal(parseShareParams("?add=../x").add, null);
  assert.equal(parseShareParams("?c=" + Array.from({ length: 14 }, () => "00126380").join(",")).ids.length, 10);
  assert.ok(ID_RE.test("00126380") && ID_RE.test("S3e4295b28f") && !ID_RE.test("126380"));
  assert.match(generateEmbedCode(u), /embed=1/);
});
test("이미지 글자 줄바꿈: 긴 이름도 잘리지 않고 모두 보인다(줄 수 한도 안에서)", () => {
  const measure = t => [...t].length * 20;                                        // 글자당 20px
  const r = wrapLines(measure, "아주아주긴회사이름입니다확인용", 200, 2);
  assert.equal(r.truncated, false); assert.equal(r.lines.join(""), "아주아주긴회사이름입니다확인용"); assert.ok(r.lines.every(l => measure(l) <= 200));
  const t = wrapLines(measure, "가".repeat(60), 200, 2); assert.equal(t.truncated, true); assert.equal(t.lines.length, 2);                 // 한도를 넘는 극단적인 경우만 말줄임
  assert.deepEqual(wrapLines(measure, "짧음", 200, 2), { lines: ["짧음"], truncated: false });
});

const E = (code, legal, display = "", flags = 7) => [code, legal, display, "", flags, 100];
const ents = buildFinder([E("00126380", "삼성전자(주)", "삼성전자"), E("00164779", "에스케이하이닉스(주)", "SK하이닉스"), E("00264779", "SK하이닉스시스템(주)"), E("S0123456789", "주식회사 사람인기업", "사람인기업"), E("00300000", "동일금액(주)", "동일금액")]);
const rk = { inds: ["반도체", "자동차"], rows: [["00126380", "삼성전자", 153628246, 0, 2025, 0, 0], ["00164779", "SK하이닉스", 120000000, 0, 2025, 0, 0], ["S0123456789", "사람인기업", 130000000, 1, 2025, -1, 0], ["00300000", "동일금액", 120000000, 0, 2025, 1, 0]] };
const cos = makeCompanies(ents, rk), by = id => cos.find(c => c.id === id);
test("기업별 순위: DART 기준(기본)과 통합 참고 순위를 구분, 공동 순위, 업종 내 순위", () => {
  const d = companyRankInfo(cos, by("00164779"), "dart", "반도체"); assert.deepEqual([d.rank, d.total, d.indRank, d.indTotal], [2, 3, 2, 2]);       // 동일금액(00300000)과 공동 2위
  const a = companyRankInfo(cos, by("00164779"), "all", "반도체"); assert.deepEqual([a.rank, a.total], [3, 4]);                                      // 사람인 130,000,000 포함 시 3위
  assert.equal(companyRankInfo(cos, by("S0123456789"), "dart").has, false); assert.match(companyRankInfo(cos, by("S0123456789"), "dart").reason, /DART 기준 순위가 없습니다/);
  assert.equal(companyRankInfo(cos, by("S0123456789"), "all").has, true); assert.equal(companyRankInfo(cos, by("S0123456789"), "all").industry, null);   // 분류 없음: 업종 순위 없음
  assert.equal(companyRankInfo(cos, by("00264779"), "all").has, false);                                                                        // 자료 없는 기업
});
test("업종별 순위: 해당 업종만, 기준에 맞는 기업만, 분류 없는 기업은 어느 업종에도 들어가지 않는다", () => {
  const t = topByIndustry(cos, 0, "dart"); assert.deepEqual(t.top.map(x => x.id), ["00126380", "00164779"]); assert.equal(t.total, 2);
  assert.equal(topByIndustry(cos, 0, "all").total, 2); assert.equal(topByIndustry(cos, -1, "all").total, 1);         // ind=-1 은 '분류 없음'이며 업종 목록에는 쓰이지 않는다
});
test("초성 검색과 동명 법인 구분(식별자 유지)", () => {
  assert.equal(chosung("삼성전자"), "ㅅㅅㅈㅈ"); assert.equal(searchFinder(ents, "ㅅㅅㅈㅈ").results[0].code, "00126380");
  assert.deepEqual(searchFinder(ents, "하이닉스").results.map(r => r.code).sort(), ["00164779", "00264779"]);        // 이름이 비슷한 서로 다른 법인은 별개 식별자
  assert.equal(searchFinder(ents, "SK하이닉스").results[0].code, "00164779");
});

const real = new URL("../../site/data/rank/rank.json", import.meta.url), realEnt = new URL("../../site/data/finder/entities.json", import.meta.url);
test("실제 공개 데이터: 4,000곳(DART 2,071·사람인 1,929), 식별자 유일, 연봉 내림차순, 주요 기업 순위", { skip: !existsSync(real) }, () => {
  const R = JSON.parse(readFileSync(real, "utf8")), E2 = JSON.parse(readFileSync(realEnt, "utf8"));
  assert.equal(R.rows.length, 4000); assert.equal(R.rows.filter(r => r[3] === 0).length, 2071); assert.equal(R.rows.filter(r => r[3] === 1).length, 1929);
  assert.equal(new Set(R.rows.map(r => r[0])).size, 4000); assert.ok(R.rows.every((r, i) => i === 0 || r[2] <= R.rows[i - 1][2]) && R.rows.every(r => ID_RE.test(r[0]) && r[2] > 0));
  const known = new Set(E2.map(r => r[0])); assert.ok(R.rows.every(r => known.has(r[0])));                                  // 모든 행이 검색 색인 기업
  const cs = makeCompanies(buildFinder(E2), R), sec = cs.find(c => c.id === "00126380"), dart = companyRankInfo(cs, sec, "dart", R.inds[sec.ind]);
  assert.ok(dart.has && dart.rank >= 1 && dart.total === 2071 && dart.indTotal > 5);
  assert.equal(companyRankInfo(cs, cs.find(c => c.id === "S3e4295b28f"), "dart").has, false);                                // 사람인 전용은 DART 기준 순위 없음
  assert.ok(R.inds.length === 60 && R.rows.filter(r => r[5] >= 0).every(r => ID_RE.test(r[0]) && /^\d{8}$/.test(r[0])));      // 업종 분류는 DART 기업에만
});
