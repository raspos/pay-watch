import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { optionLabel, fmtPct, annualMan, fmtMan, series, vsAll, binTable, filterItems, chartGeom, niceMax, lastOverFirst, KIND } from "../../web/js/lab-core.js";

const LAB = JSON.parse(readFileSync(new URL("../../site/data/lab/lab.json", import.meta.url), "utf8"));
const find = (k, name) => LAB[k].find(x => x.name === name);

test("월임금총액(천원)→연환산(만원)=×1.2, 반올림은 표시에서만", () => {
  assert.equal(annualMan(4482), 5378.4);              // 전체 평균 4,482천원
  assert.equal(annualMan(null), null);
  assert.equal(fmtMan(5378.4), "5,378만원");
  assert.equal(fmtMan(null), "비공개·자료 없음");
  assert.ok(Math.abs(annualMan(3133) - 3759.6) < 1e-9);
});
test("산업=근속, 직종=경력을 섞지 않는다", () => {
  assert.equal(KIND.industry.axis, "근속연수"); assert.equal(KIND.occupation.axis, "경력연수");
  assert.equal(LAB.meta.bins.industry.length, 5); assert.equal(LAB.meta.bins.occupation.length, 5);
  // 같은 '전체' 합계(4,482천원)지만 구간별 근로자 분포는 서로 다르다(두 표가 섞이지 않았다는 증거)
  const i = find("industry", "전체"), o = find("occupation", "전직종");
  assert.equal(i.mAll, 4482); assert.equal(o.mAll, 4482);
  assert.notDeepEqual(i.n, o.n);
  assert.equal(i.n[0], 2000172); assert.equal(o.n[0], 1219556);
});
test("원자료 값 일치(제조업 근속, 판매 종사자 경력)", () => {
  const mf = find("industry", "제조업"); assert.deepEqual(series(mf).map(Math.round), [3760, 4440, 5003, 5558, 8214]); // PHASE 1 표와 동일
  const sale = find("occupation", "판매 종사자"); assert.ok(Math.abs(sale.m[0] * 1.2 - 2984.4) < 1e-9); assert.equal(sale.m[4] * 1.2, 6397.2);
});
test("결측은 null, 0이 아니며 그래프에서 선을 끊는다", () => {
  const nulls = [...LAB.industry, ...LAB.occupation].filter(it => it.m.includes(null));
  assert.ok(nulls.length >= 1);
  for (const it of [...LAB.industry, ...LAB.occupation]) { for (const v of [...it.m, ...it.n]) assert.ok(v === null || v > 0); }
  const g = chartGeom([[100, null, 300, 400, 500]]);
  assert.equal(g.series[0].segs.length, 2); assert.equal(g.series[0].pts[1], null);
  assert.equal(vsAll({ m: [null, 1, 1, 1, 1], n: [], mAll: 1 }, 0).diff, null);
  assert.equal(lastOverFirst({ m: [null, 1, 1, 1, 2] }), null);
});
test("전체 평균과의 차이·구간 비교", () => {
  const it = { m: [2000, 3000, 4000, 5000, 6000], n: [1, 2, 3, 4, 5], mAll: 4000 };
  const r = vsAll(it, 4); assert.equal(Math.round(r.diff), 2400); assert.ok(Math.abs(r.pct - 0.5) < 1e-12);
  const t = binTable(it, ["a", "b", "c", "d", "e"], 2); assert.equal(t[2].vsSel, null); assert.ok(Math.abs(t[4].vsSel - 0.5) < 1e-12);
  assert.ok(Math.abs(lastOverFirst(it) - 3) < 1e-12);
});
test("분류 검색", () => {
  assert.ok(filterItems(LAB.industry, "금융").length >= 1);
  assert.ok(filterItems(LAB.occupation, "사무").length >= 1);
  assert.equal(filterItems(LAB.industry, "존재하지않는분류xyz").length, 0);
  assert.equal(filterItems(LAB.industry, "").length, LAB.industry.length);
});
test("그래프 좌표: 5구간 균등, 0 기준 축, 값이 클수록 위", () => {
  const g = chartGeom([[10, 20, 30, 40, 50]]);
  const p = g.series[0].pts; assert.equal(p.length, 5);
  assert.ok(p[0].x < p[1].x && p[3].x < p[4].x); assert.ok(p[4].y < p[0].y);
  assert.equal(niceMax(5378 * 1.05), 6000); assert.equal(niceMax(11186), 12000); assert.equal(niceMax(0), 1000); assert.ok(g.ymax >= 50);
});
test("표시 문자열: 부호 통일, 분류 라벨", () => {
  assert.equal(fmtPct(0.495), "+49.5%"); assert.equal(fmtPct(-0.146), "−14.6%"); assert.equal(fmtPct(null), "-");
  assert.equal(optionLabel({ name: "제조업", level: "대분류", code: "C(10~34)" }), "제조업 [대분류] (10~34)");
  assert.equal(optionLabel({ name: "식료품 제조업", level: "중분류", code: null }), "· 식료품 제조업");
  assert.equal(optionLabel({ name: "관리자", level: "대분류", code: "1" }), "관리자 [대분류] (1)");
});
