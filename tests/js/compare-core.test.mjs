import assert from "node:assert/strict";
import test from "node:test";
import { CAP_NEAR, MAX_ITEMS, ROWS, evaluateAll, evaluateRow, fmtValue, fromCorp, fromWorkplace, parseItems } from "../../web/js/compare-core.js";

const row = id => ROWS.find(r => r.id === id);
const corp = (o = {}) => ({
  code: o.code ?? "00000001", n: o.n ?? "(주)가나다", loc: "서울", scope: o.scope ?? 0.95,
  dart: o.dart === null ? null : { avg: 100_000_000, level: "ok", tenure: 10, fy: 2025, pos: { top_pct: 20, n: 40 }, ...(o.dart || {}) },
  nps: { est: 60_000_000, cap: 0.5, subs: 1000, g12: 0.02, series: { est: [58_000_000, ...Array(11).fill(59_000_000), 60_000_000], cap: Array(13).fill(0.5) }, ...(o.nps || {}) },
});
const E = (o) => fromCorp(corp(o));

test("공시 평균급여: 일관성 통과 회사끼리만 비교, 최고값만 강조", () => {
  const ents = [E({ n: "A", dart: { avg: 150_000_000 } }), E({ n: "B", dart: { avg: 120_000_000 } }), E({ n: "C", dart: { avg: 99_000_000, level: "caution" } })];
  const r = evaluateRow(row("dart_avg"), ents);
  assert.deepEqual(r.values, [150_000_000, 120_000_000, null]);   // 주의 등급은 비교에서 제외
  assert.equal(r.comparable, true);
  assert.deepEqual(r.leaders, [0]);
});

test("공시가 한 곳뿐이면 우열을 가리지 않는다", () => {
  const r = evaluateRow(row("dart_avg"), [E({}), E({ dart: null })]);
  assert.equal(r.comparable, false);
  assert.deepEqual(r.leaders, []);
  assert.match(r.reason, /한 곳뿐/);
});

test("국민연금 추정: 상한 접근 회사가 있으면 승패 없음(막대용 값은 남김)", () => {
  const ents = [E({ n: "A", nps: { est: 78_000_000, cap: 0.99 } }), E({ n: "B", nps: { est: 50_000_000, cap: 0.6 } })];
  const r = evaluateRow(row("nps_est"), ents);
  assert.equal(r.comparable, false);
  assert.deepEqual(r.leaders, []);
  assert.deepEqual(r.capped, [0]);
  assert.match(r.reason, /A/);
  assert.equal(r.values[0], 78_000_000);
});

test("국민연금 추정: 모두 상한 비접근이면 비교한다", () => {
  const ents = [E({ nps: { est: 55_000_000, cap: 0.6 } }), E({ nps: { est: 50_000_000, cap: CAP_NEAR - 0.01 } })];
  const r = evaluateRow(row("nps_est"), ents);
  assert.equal(r.comparable, true);
  assert.deepEqual(r.leaders, [0]);
});

test("상한 접근도 정확히 0.9 이면 접근으로 본다", () => {
  const r = evaluateRow(row("nps_est"), [E({ nps: { est: 60e6, cap: CAP_NEAR } }), E({ nps: { est: 50e6, cap: 0.5 } })]);
  assert.equal(r.comparable, false);
});

test("12개월 추정급여 변화: 시작·끝 달 중 하나라도 상한 접근이면 계산하지 않는다", () => {
  const capped = fromCorp(corp({ nps: { series: { est: [60e6, ...Array(11).fill(60e6), 66e6], cap: [0.5, ...Array(11).fill(0.5), 0.95] } } }));
  assert.equal(capped.payChange, null);
  const ok = fromCorp(corp({ nps: { series: { est: [50e6, ...Array(11).fill(51e6), 52.5e6], cap: Array(13).fill(0.4) } } }));
  assert.ok(Math.abs(ok.payChange - 0.05) < 1e-9);
  const r = evaluateRow(row("pay_change"), [capped, ok]);
  assert.equal(r.comparable, false);                 // 값이 한 곳뿐
});

test("가입자 수: 확인된 사업장 범위가 공시 직원 수와 크게 다르면 우열 없음", () => {
  const ents = [E({ n: "기아형", scope: 0.18, nps: { subs: 6500 } }), E({ n: "B", scope: 1.0, nps: { subs: 9000 } })];
  const r = evaluateRow(row("subs"), ents);
  assert.equal(r.comparable, false);
  assert.match(r.reason, /기아형/);
  const ok = evaluateRow(row("subs"), [E({ scope: 0.9, nps: { subs: 100 } }), E({ scope: 1.1, nps: { subs: 300 } })]);
  assert.equal(ok.comparable, true);
  assert.deepEqual(ok.leaders, [1]);
});

test("사업장끼리의 가입자 수 비교는 범위 제한이 없다", () => {
  const w = d => fromWorkplace({ id: d.id, n: d.n, loc: "x", pp: true, e: [60e6], c: [0.5], s: [d.s], m: { g12: 0.1, pc12: 0.02 } });
  const r = evaluateRow(row("subs"), [w({ id: 1, n: "P", s: 50 }), w({ id: 2, n: "Q", s: 80 })]);
  assert.equal(r.comparable, true);
  assert.deepEqual(r.leaders, [1]);
});

test("증감률: 음수도 비교, 동률은 모두 강조, 전부 같으면 강조 없음", () => {
  const mk = g => E({ nps: { g12: g } });
  assert.deepEqual(evaluateRow(row("g12"), [mk(-0.1), mk(-0.03)]).leaders, [1]);
  assert.deepEqual(evaluateRow(row("g12"), [mk(0.05), mk(0.05), mk(0.01)]).leaders, [0, 1]);
  assert.deepEqual(evaluateRow(row("g12"), [mk(0.05), mk(0.05)]).leaders, []);
  const r = evaluateRow(row("g12"), [mk(-0.1), mk(0.04)]);
  assert.equal(r.maxAbs, 0.1);
});

test("동종업계 위치는 어떤 경우에도 승패를 표시하지 않는다", () => {
  const r = evaluateRow(row("pos"), [E({}), E({})]);
  assert.equal(r.comparable, false);
  assert.deepEqual(r.leaders, []);
  assert.match(r.reason, /비교집단/);
});

test("공시 값과 추정 값은 서로 다른 항목으로만 다룬다(섞어 순위를 만들지 않음)", () => {
  const ents = [E({ dart: { avg: 200e6 }, nps: { est: 50e6, cap: 0.5 } }), E({ dart: null, nps: { est: 70e6, cap: 0.5 } })];
  const all = evaluateAll(ents);
  const d = all.rows.find(x => x.row.id === "dart_avg").res, n = all.rows.find(x => x.row.id === "nps_est").res;
  assert.equal(d.comparable, false);                // 공시는 한 곳뿐
  assert.deepEqual(n.leaders, [1]);                 // 추정은 추정끼리
  assert.ok(!("overall" in all) && !("winner" in all));   // 종합 승자 없음
});

test("URL: items 파싱, 중복 제거, 최대 4개, 잘못된 토큰 무시, 예전 a/b 호환", () => {
  assert.deepEqual(parseItems("?items=c0001,w22,c0001,x9,w33,c0004,w55"), ["c0001", "w22", "w33", "c0004"]);
  assert.equal(parseItems("?items=c1,c2,c3,c4,c5,c6").length, MAX_ITEMS);
  assert.deepEqual(parseItems("?a=228151&b=142733"), ["w228151", "w142733"]);
  assert.deepEqual(parseItems(""), []);
});

test("값 표기: 없는 값은 자료 없음, 0 으로 채우지 않는다", () => {
  assert.equal(fmtValue(row("dart_avg"), null), "자료 없음");
  assert.equal(fmtValue(row("dart_avg"), 153_630_000), "15,363만원");
  assert.equal(fmtValue(row("g12"), -0.0321), "-3.2%");
  assert.equal(fmtValue(row("g12"), 0.1), "+10.0%");
  assert.equal(fmtValue(row("tenure"), 13.66), "13.7년");
});

test("값이 없는 이유를 밝힌다(상한 접근으로 변화율을 계산하지 않은 회사)", () => {
  const r = evaluateRow(row("pay_change"), [E({ n: "가", nps: { series: { est: [60e6, ...Array(12).fill(60e6)], cap: [0.95, ...Array(12).fill(0.95)] } } }), E({ n: "나", nps: { series: { est: [60e6, ...Array(12).fill(60e6)], cap: [0.95, ...Array(12).fill(0.95)] } } })]);
  assert.equal(r.comparable, false);
  assert.match(r.reason, /상한에 접근했거나/);
  assert.match(r.reason, /가, 나/);
});
