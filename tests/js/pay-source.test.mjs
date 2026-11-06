// 대표 평균연봉 소스 선택: DART(유효) → 사람인 추정 → 자료 없음(null). 소스별 원본값은 서로 덮어쓰지 않는다.
import test from "node:test";
import assert from "node:assert/strict";
import { pickRepresentative, SOURCES } from "../../web/js/pay-source.js";
import { fromEntity, fromCorp, evaluateAll, parseItems } from "../../web/js/compare-core.js";
import { shardKey } from "../../web/js/saramin.js";
import { category, resultHref, FLAG } from "../../web/js/finder-core.js";

const D = { avg: 153628246, level: "ok", fy: 2025, src: "https://dart.fss.or.kr/x" };
const SM = { v: 85000000, y: 2025 };
test("1순위: 유효한 DART 평균급여가 있으면 사람인 값이 있어도 DART 를 쓰고, 두 원본값은 그대로 남는다", () => {
  const c = { dart: D, saramin: SM }; const r = pickRepresentative(c);
  assert.equal(r.source, "dart"); assert.equal(r.value, 153628246); assert.equal(r.estimate, false); assert.equal(r.reason, "dart_valid");
  assert.equal(c.dart.avg, 153628246); assert.equal(c.saramin.v, 85000000);
});
test("2순위: DART 가 없으면 사람인 추정(estimate=true, 표시연도 보존)", () => {
  const r = pickRepresentative({ dart: null, saramin: SM }); assert.equal(r.source, "saramin"); assert.equal(r.value, 85000000); assert.equal(r.estimate, true); assert.equal(r.year, 2025); assert.equal(r.reason, "dart_missing");
});
test("DART 가 품질 문제로 보류(일관성 미확인·확인 중)이면 사람인으로 대체하되 이유를 기록, 사람인도 없으면 보류 안내", () => {
  assert.equal(pickRepresentative({ dart: { ...D, level: "caution" }, saramin: SM }).reason, "dart_held_quality");
  assert.equal(pickRepresentative({ dart: null, hold: 1, saramin: SM }).reason, "dart_held_quality");
  assert.equal(pickRepresentative({ dart: null, hold: 1 }).kind, "hold"); assert.equal(pickRepresentative({ dart: { ...D, level: "caution" } }).kind, "hold");
});
test("3순위: 자료가 없으면 null 처리(값을 만들지 않음), 국민연금 역산값은 소스가 아니다", () => {
  assert.deepEqual(pickRepresentative({ dart: null }), { kind: "none" }); assert.deepEqual(pickRepresentative(null), { kind: "none" });
  assert.deepEqual(pickRepresentative({ dart: null, nps: { est: 78232938 } }), { kind: "none" });
  assert.equal(SOURCES.map(s => s.id).join(), "dart,saramin");
});
test("CJ 처럼 이례적인 공시값도 유효한 DART 이면 사람인으로 자동 대체하지 않는다", () => {
  const r = pickRepresentative({ dart: { ...D, avg: 736437500 }, saramin: { v: 104990000, y: 2025 } }); assert.equal(r.source, "dart"); assert.equal(r.value, 736437500);
});
test("사람인 전용 기업: 식별자 규칙·링크·분류(DART 코드를 만들지 않는다)", () => {
  const e = { code: "S0123456789", legal: "주식회사 예시", display: "예시", flags: FLAG.SM | FLAG.SMONLY };
  assert.equal(resultHref(e), "company.html?sm=S0123456789"); assert.equal(resultHref({ code: "00126380" }), "company.html?corp=00126380"); assert.equal(category(e), "e");
  assert.equal(category({ flags: FLAG.PAY | FLAG.SM }), "b");                      // DART 우선
  assert.equal(shardKey("00126380"), 126380 % 64); assert.equal(shardKey("S0123456789"), parseInt("012345", 16) % 64);
});
test("비교: 사람인 전용·자료 없는 기업, 출처가 다른 값은 서로 우열을 가리지 않는다", () => {
  const a = fromEntity({ code: "00126371", legal: "삼성전기(주)" }); assert.equal(a.noData, true); assert.equal(a.key, "c00126371");
  const s1 = fromEntity({ code: "Sabcdef0123", legal: "가나다", display: "가나다" }, { saramin: SM }); assert.equal(s1.key, "sabcdef0123"); assert.equal(s1.noData, false); assert.equal(s1.dart, null);
  const b = { code: "00126380", n: "삼성전자(주)", loc: "x", dart: D, saramin: { v: 90000000, y: 2025 }, nps: { series: { est: [1, 2], cap: [0.5, 0.5] }, est: 2, cap: 0.5, subs: 1, g12: 0 }, scope: 1 };
  const all = evaluateAll([s1, fromCorp(b)]);
  assert.equal(all.rows.find(x => x.row.id === "dart_avg").res.comparable, false);        // DART 는 한쪽뿐
  const sm = all.rows.find(x => x.row.id === "saramin_avg"); assert.equal(sm.res.comparable, true);   // 사람인끼리만 비교
  assert.deepEqual(parseItems("?items=c00126371,sabcdef0123,w1,zzz"), ["c00126371", "sabcdef0123", "w1"]);
});
