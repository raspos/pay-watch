// DART 급여가 품질 문제로 보류된 기업의 공시값이 어떤 화면·그래프 데이터에도 쓰이지 않는지(회귀 테스트). 화면 문자열뿐 아니라 그래프 데이터 생성 로직도 검사한다.
import test from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { visibleDartAvg, pickRepresentative } from "../../web/js/pay-source.js";
import { fromCorp, evaluateAll } from "../../web/js/compare-core.js";

const root = new URL("../../", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "heldsec-"));
for (const f of ["web/js/est-section.js", "web/js/est-core.js", "web/js/common.js", "web/js/site-config.js"]) cpSync(new URL(f, root), join(dir, f.split("/").pop()));
const sec = await import(pathToFileURL(join(dir, "est-section.js")).href);
const core = await import(pathToFileURL(join(dir, "est-core.js")).href);

const HELD_AVG = 74090000;                                           // 보류된 공시 평균급여(예시값)
const OK = { avg: 153628246, level: "ok", fy: 2025 }, HELD = { avg: HELD_AVG, level: "caution", fy: 2025, consistency: 0.2 };

test("보여도 되는 DART 평균급여는 level=ok 일 때만", () => {
  assert.equal(visibleDartAvg({ dart: OK }), 153628246);
  for (const c of [{ dart: HELD }, { dart: { ...OK, level: "unverified" } }, { dart: null, hold: 1 }, { dart: null }, null]) assert.equal(visibleDartAvg(c), null);
});
test("대표값 선택: 보류된 공시값은 사람인이 없어도 숫자로 나오지 않는다", () => {
  const r = pickRepresentative({ dart: HELD }); assert.equal(r.kind, "hold"); assert.ok(!JSON.stringify(r).includes(String(HELD_AVG)));
  const s = pickRepresentative({ dart: HELD, saramin: { v: 91360000, y: 2025 } }); assert.equal(s.value, 91360000); assert.ok(!JSON.stringify(s).includes(String(HELD_AVG)));
});
test("비교 입력과 비교 항목: 보류된 공시 평균급여는 값이 null 이라 막대·우열에 쓰이지 않는다", () => {
  const nps = { series: { est: [1, 2], cap: [0.5, 0.5] }, est: 2, cap: 0.5, subs: 1, g12: 0 };
  const held = fromCorp({ code: "00104069", n: "보류(주)", loc: "x", dart: HELD, nps, scope: 1 });
  assert.equal(held.dart.avg, null);
  const ok = fromCorp({ code: "00126380", n: "정상(주)", loc: "x", dart: OK, nps, scope: 1 });
  const row = evaluateAll([held, ok]).rows.find(x => x.row.id === "dart_avg");
  assert.deepEqual(row.res.values, [null, 153628246]); assert.equal(row.res.comparable, false);
  assert.ok(!JSON.stringify(row).includes(String(HELD_AVG)));
});
test("연구용 그래프 데이터: 보류 기업은 기준선(avgY)도 축 범위도 보류된 공시값을 쓰지 않는다", () => {
  const rec = { c: "00104069", k: "보류", s: "SENSITIVE", g: "B", a: 999999, h: false,
    b: [[3000, 4000], [4500, 5200], [5000, 6000], [6300, 7200], [8000, 9000]], x: [[2800, 4300], [4200, 5600], [4800, 6400], [6000, 7600], [7500, 9500]] };
  const held = sec.effectiveRec(rec, { dartOk: false }), ok = sec.effectiveRec(rec, { dartOk: true }), unknown = sec.effectiveRec(rec, {});
  assert.equal(held.a, null); assert.equal(rec.a, 999999);                                    // 원본은 바꾸지 않는다
  const g1 = core.chartModel(held, 3), g2 = core.chartModel(ok, 3);
  assert.equal(g1.avgY, null); assert.ok(g1.ymax < 20000);                                    // 기준선 없음, 축이 보류값(999,999)에 끌려가지 않음
  assert.ok(g2.avgY != null && g2.ymax > 900000);                                             // 정상 기업은 그대로
  assert.equal(unknown.a, 999999);                                                            // 보류 신호가 없으면(공개 빌드 밖) 기존 동작 유지
});
test("화면 소스: 결과 화면은 d.avg 를 직접 쓰지 않고, 연구용 로더에는 보류 신호가 연결돼 있다", () => {
  const corp = readFileSync(new URL("web/js/corp.js", root), "utf8");
  assert.ok(!/\bd\.avg\b/.test(corp));                                                         // 모든 공시 숫자는 visibleDartAvg 를 거친 dv
  assert.ok(corp.includes("const pair = (dartOk && n.est != null)") && corp.includes("visibleDartAvg(c)"));
  const company = readFileSync(new URL("web/js/company.js", root), "utf8"), embed = readFileSync(new URL("web/js/est-embed.js", root), "utf8");
  assert.ok(company.includes('dartOk: !!(c.dart && c.dart.level === "ok")') && embed.includes("__pwResult") && embed.includes("dartAvg"));
});

test("공개 추정 데이터에는 기업 평균(a)이 없고, 결과 화면이 넘긴 보여도 되는 DART 평균만 기준선이 된다", () => {
  const rec = { b: [[3000, 4000], [4500, 5200], [5000, 6000], [6300, 7200], [8000, 9000]], x: null, cau: 1 };
  assert.equal(sec.effectiveRec(rec, { dartAvgMan: null }).a, null);                          // 보류·없음: 기준선 없음
  assert.equal(sec.effectiveRec(rec, { dartAvgMan: 7000 }).a, 7000);                          // 정상: 표시 가능한 공시 평균(만원)
  assert.ok(core.canEstimate(rec) && core.chartModel(sec.effectiveRec(rec, { dartAvgMan: null }), 3).avgY === null);   // 등급 필드 없는 공개 레코드도 표시 대상
  assert.equal(core.canEstimate({ cau: 0 }), false);                                          // 범위 없는 레코드는 영역을 그리지 않는다
});
