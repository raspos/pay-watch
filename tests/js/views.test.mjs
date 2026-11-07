// 조회수 표시 로직(BOK워치 방식): 세션당 한 번만 POST, 이후 GET, 서버가 없거나 실패하면 표시하지 않는다.
import test from "node:test";
import assert from "node:assert/strict";
import { showViews } from "../../web/js/views.js";

const mkStorage = () => { const m = new Map(); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v) }; };
const okFetch = calls => async (url, opt) => { calls.push(opt.method); return { ok: true, json: async () => ({ total: 12345, today: 67 }) }; };
const el = () => ({ hidden: true, textContent: "" });

test("첫 방문은 POST 로 올리고 표시, 같은 세션의 이후 방문은 GET 만", async () => {
  const calls = [], st = mkStorage(), e = el();
  await showViews({ url: "https://x/views", el: e, fetchFn: okFetch(calls), storage: st });
  assert.equal(e.textContent, "조회수 오늘 67 · 누적 12,345"); assert.equal(e.hidden, false);
  await showViews({ url: "https://x/views", el: el(), fetchFn: okFetch(calls), storage: st });
  assert.deepEqual(calls, ["POST", "GET"]);
});
test("주소가 없거나 서버 실패·형식 이상이면 아무것도 표시하지 않는다", async () => {
  const e = el(), calls = [];
  assert.equal(await showViews({ url: null, el: e, fetchFn: okFetch(calls), storage: mkStorage() }), null); assert.equal(calls.length, 0); assert.equal(e.hidden, true);
  assert.equal(await showViews({ url: "u", el: e, fetchFn: async () => ({ ok: false }), storage: mkStorage() }), null);
  assert.equal(await showViews({ url: "u", el: e, fetchFn: async () => { throw new Error("net"); }, storage: mkStorage() }), null);
  assert.equal(await showViews({ url: "u", el: e, fetchFn: async () => ({ ok: true, json: async () => ({ total: "x" }) }), storage: mkStorage() }), null);
  assert.equal(e.hidden, true);
});
test("저장소를 못 써도(사생활 보호 모드) 동작하고 개인 식별 정보는 보내지 않는다", async () => {
  const seen = [], bad = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } }, e = el();
  await showViews({ url: "u", el: e, fetchFn: async (url, opt) => { seen.push(opt); return { ok: true, json: async () => ({ total: 1, today: 1 }) }; }, storage: bad });
  assert.equal(e.hidden, false); assert.deepEqual(Object.keys(seen[0]).sort(), ["cache", "method"]);                 // 본문·헤더·식별자 없음
});
