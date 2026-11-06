// web_exp/js/exp-core.js 순수 로직 테스트. 이 모듈은 사이트의 common.js 를 import 하므로 임시 폴더에 함께 복사해 불러온다.
import test from "node:test";
import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const root = new URL("../../", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "expcore-"));
cpSync(new URL("web_exp/js/exp-core.js", root), join(dir, "exp-core.js"));
cpSync(new URL("web/js/common.js", root), join(dir, "common.js"));
const core = await import(pathToFileURL(join(dir, "exp-core.js")).href);
const { fmtEok, fmtRange, relWidth, isWide, resolveBin, chartModel, parseQuery, buildQuery, shardOf, reasonText, canEstimate, BINS, BIN_LABEL, DEFAULT_BIN, gradeOf, displayMode } = core;

const REC = { c: "00126380", k: "삼성전자", s: "SENSITIVE", g: "B", a: 15363, w: ["THRESHOLD_BAND(1.25~2.00)"], h: false,
  b: [[6811, 7417], [8983, 9781], [10230, 11140], [11624, 12660], [16661, 18146]], x: [[6274, 9544], [8000, 10300], [9000, 12000], [10932, 12843], [16548, 18576]] };
const HELD = { ...REC, c: "1", h: true, x: null };
const NA = { c: "2", k: "무", s: "INVALID", g: "C", a: 5000, w: ["NO_INDUSTRY_CODE"], b: null, x: null };

test("금액 단위 변환(만원 → 억·만)", () => {
  assert.equal(fmtEok(11624), "1억 1,624만"); assert.equal(fmtEok(9317), "9,317만"); assert.equal(fmtEok(20000), "2억"); assert.equal(fmtEok(10932), "1억 932만"); assert.equal(fmtEok(null), null);
  assert.equal(fmtRange([11624, 12660]), "1억 1,624만 ~ 1억 2,660만원"); assert.equal(fmtRange(null), null);
});
test("5개 근속 구간 전환과 기본·확대 범위 구분", () => {
  assert.equal(BINS.length, 5); assert.deepEqual(BIN_LABEL, ["1년 미만", "1~3년", "3~5년", "5~10년", "10년 이상"]);
  const r = resolveBin(REC, 3); assert.deepEqual(r.base, [11624, 12660]); assert.deepEqual(r.exp, [10932, 12843]); assert.equal(r.held, false);
  const r0 = resolveBin(REC, 0); assert.deepEqual(r0.base, [6811, 7417]); assert.deepEqual(r0.exp, [6274, 9544]);
  assert.notDeepEqual(resolveBin(REC, 1).base, resolveBin(REC, 2).base);
});
test("형태 실험 보류와 추정 불가는 금액을 만들지 않는다", () => {
  const h = resolveBin(HELD, 3); assert.equal(h.exp, null); assert.equal(h.held, true); assert.deepEqual(h.base, [11624, 12660]);
  assert.equal(canEstimate(HELD), true); assert.equal(canEstimate(NA), false);
  assert.deepEqual(resolveBin(NA, 3), { kind: "na" });
  assert.equal(chartModel(NA), null);
});
test("폭 30% 경고(설명용 기준)", () => {
  assert.ok(Math.abs(relWidth([100, 130]) - 30 / 115) < 1e-12);
  assert.equal(isWide([100, 150]), true); assert.equal(isWide([100, 120]), false); assert.equal(isWide(null), false);
  assert.equal(resolveBin(REC, 0).expWide, true); assert.equal(resolveBin(REC, 3).expWide, false);
});
test("실제 연구용 색인 3,912곳: 식별자 일치, 샤드 값이 저장 결과와 같음(빌드된 경우)", () => {
  const p = new URL("preview/data/exp/index.json", root);
  if (!existsSync(p)) return;
  const idx = JSON.parse(readFileSync(p, "utf8")); assert.equal(idx.length, 3912);
  assert.ok(idx.every(x => /^\d{8}$/.test(x[0]) && ["A", "B", "C", "D"].includes(x[3])));
  const sh = JSON.parse(readFileSync(new URL(`preview/data/exp/f/${shardOf("00126380")}.json`, root), "utf8"))["00126380"];
  assert.deepEqual(resolveBin(sh, 3).base, [11623, 12659]); assert.deepEqual(resolveBin(sh, 3).exp, [10931, 12842]);
});
test("등급별 표시 방식: A·B 범위, C 공시 평균만(범위 없음), D 값 없음. 등급 누락은 가장 보수적인 D", () => {
  assert.equal(displayMode({ g: "A" }), "range"); assert.equal(displayMode({ g: "B" }), "range"); assert.equal(displayMode({ g: "C" }), "pay"); assert.equal(displayMode({ g: "D" }), "none");
  assert.equal(gradeOf({}), "D"); assert.equal(displayMode({}), "none"); assert.equal(gradeOf(null), "D");
  // 데이터에 범위가 있어도 C·D 이면 금액을 만들지 않는다(이중 방어; 실제 데이터에는 범위 자체가 없다)
  assert.equal(canEstimate({ ...REC, g: "C" }), false); assert.deepEqual(resolveBin({ ...REC, g: "D" }, 3), { kind: "na" }); assert.equal(chartModel({ ...REC, g: "C" }), null);
  assert.equal(canEstimate({ ...REC, g: "A" }), true); assert.equal(canEstimate(REC), true);
  // PHASE 14: C·D 는 추정 영역 자체를 렌더링하지 않는다(canEstimate=false 이면 mountEstimate 가 아무것도 그리지 않음)
});
test("기본 근속 구간은 5~10년(검색 직후 숫자가 보이도록), URL 의 구간 지정은 그대로", () => {
  assert.equal(DEFAULT_BIN, 3); assert.equal(BIN_LABEL[DEFAULT_BIN], "5~10년"); assert.deepEqual(parseQuery("?c=00126380"), { code: "00126380", bin: null });
});
test("실제 연구용 데이터: C·D 기업의 JSON 에 범위가 없고 D 에는 공시 값도 없다(빌드된 경우)", () => {
  const dir = new URL("preview/data/exp/f/", root); if (!existsSync(dir)) return;
  let n = 0;
  for (let i = 0; i < 64; i++) for (const r of Object.values(JSON.parse(readFileSync(new URL(`${i}.json`, dir), "utf8")))) {
    n++; if (r.g === "C" || r.g === "D") assert.ok(r.b === null && r.x === null, r.c);
    if (r.g === "D") assert.ok(r.a === null && r.t === null && r.e === null, r.c);
  }
  assert.equal(n, 3912);
});
test("그래프 모델: 5개 구간 막대, 구간 사이 보간 없음, 기본·확대 구분", () => {
  const g = chartModel(REC, 3); assert.equal(g.bars.length, 5); assert.equal(g.bars.filter(b => b.selected).length, 1); assert.equal(g.bars[3].selected, true);
  assert.ok(g.bars.every(b => b.exp && b.yb[0] < b.yb[1] && b.ye[0] <= b.yb[0] + 1e-9 && b.ye[1] >= b.yb[1] - 1e-9));   // 확대 막대가 기본 막대를 감싼다
  assert.ok(g.avgY != null && g.ymax > 18576 && g.ymin <= 6274);
  const gh = chartModel(HELD, 2); assert.ok(gh.bars.every(b => b.exp === null && b.ye === null));
});
test("URL 상태와 샤드 규칙", () => {
  assert.deepEqual(parseQuery("?c=00126380&b=3"), { code: "00126380", bin: 3 }); assert.deepEqual(parseQuery("?c=126380"), { code: null, bin: null }); assert.deepEqual(parseQuery("?c=00126380&b=7"), { code: "00126380", bin: null });
  assert.equal(buildQuery("00126380", 3), "?c=00126380&b=3"); assert.equal(buildQuery("00126380", null), "?c=00126380"); assert.equal(shardOf("00126380"), 126380 % 64);
});
test("사유 문구: 알려진 코드는 설명, 매개변수 붙은 코드도 처리", () => {
  assert.match(reasonText("THRESHOLD_BAND(1.25~2.00)"), /산업 임금곡선/); assert.match(reasonText("MATH_INFEASIBLE:M10_RANGE_EMPTY"), /계산할 수 없습니다/); assert.match(reasonText("MAPPING_SUSPECT_LEVEL(공시/산업 평균 8.44)"), /4배/);
});
