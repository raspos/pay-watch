import assert from "node:assert/strict";
import test from "node:test";
import { SHOW, dartEligibility, diffPct, higherThan, npsEligibility } from "../../web/js/peers-core.js";

const items = [[1, "가", 90, 100, "x"], [2, "나", 80, 50, "x"], [3, "다", 70, 30, "x"], [4, "라", 60, 20, "x"]];

test("자기보다 높은 곳만, 높은 순으로, 자기 자신은 제외", () => {
  assert.deepEqual(higherThan(items, 65).map(i => i[0]), [1, 2, 3]);
  assert.deepEqual(higherThan(items, 65, [2]).map(i => i[0]), [1, 3]);
  assert.deepEqual(higherThan(items, 65, ["1"]).map(i => i[0]), [2, 3]);       // 문자열 id 도 제외
});

test("값이 같으면 높은 곳이 아니다(엄격 비교)", () => {
  assert.deepEqual(higherThan(items, 80).map(i => i[0]), [1]);
});

test("이미 최상위면 빈 목록, 값이 없으면 빈 목록(0 으로 취급하지 않음)", () => {
  assert.deepEqual(higherThan(items, 95), []);
  assert.deepEqual(higherThan(items, null), []);
  assert.deepEqual(higherThan(items, undefined), []);
});

test("표시 개수 제한", () => {
  const many = Array.from({ length: 30 }, (_, i) => [i, `n${i}`, 1000 - i, 1, "x"]);
  assert.equal(higherThan(many, 0).length, SHOW);
  assert.equal(higherThan(many, 0, [], 3).length, 3);
  assert.equal(higherThan(many, 0)[0][0], 0);
});

test("국민연금 추정 목록: 상한 접근(0.9 이상)이면 만들지 않는다", () => {
  assert.equal(npsEligibility({ est: 7e7, cap: 0.95, gid: 3 }).ok, false);
  assert.match(npsEligibility({ est: 7e7, cap: 0.95, gid: 3 }).reason, /하한값/);
  assert.equal(npsEligibility({ est: 7e7, cap: 0.9, gid: 3 }).ok, false);        // 경계값은 접근
  assert.equal(npsEligibility({ est: 5e7, cap: 0.89, gid: 3 }).ok, true);
});

test("국민연금 추정 목록: 비교집단이나 추정값이 없으면 이유를 밝히고 만들지 않는다", () => {
  assert.equal(npsEligibility({ est: 5e7, cap: 0.5, gid: null }).ok, false);
  assert.match(npsEligibility({ est: 5e7, cap: 0.5, gid: undefined }).reason, /비교집단/);
  assert.equal(npsEligibility({ est: null, cap: null, gid: 1 }).ok, false);
});

test("공시 목록: 일관성 통과 + 비교집단이 있을 때만", () => {
  assert.equal(dartEligibility(null).ok, false);
  assert.equal(dartEligibility({ level: "caution", pos: { gid: 1 } }).ok, false);
  assert.equal(dartEligibility({ level: "ok", pos: null }).ok, false);
  assert.match(dartEligibility({ level: "ok", pos: null }).reason, /30곳 미만/);
  assert.equal(dartEligibility({ level: "ok", pos: { gid: 0 } }).ok, true);        // gid 0 도 유효
});

test("차이율 계산", () => {
  assert.ok(Math.abs(diffPct(100, 118) - 0.18) < 1e-9);
  assert.equal(diffPct(0, 5), null);
});
