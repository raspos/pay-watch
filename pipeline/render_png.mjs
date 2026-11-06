// PAY RANK 공유 이미지(PNG) 렌더 검증용: 로컬 서버의 rank.html 에서 실제 렌더러(rank-share.js)로 이미지를 만들어 파일로 저장한다(사람 눈으로 확인하는 용도).
// 사용: node pipeline/render_png.mjs [포트=8793] [출력폴더=docs/screenshots/phase14_4]   (127.0.0.1 로컬 서버만 대상)
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const port = process.argv[2] || "8793";
const out = process.argv[3] || fileURLToPath(new URL("../docs/screenshots/phase14_4", import.meta.url));
mkdirSync(out, { recursive: true });
const prof = mkdtempSync(join(tmpdir(), "png-")), DBG = 9334;
const proc = spawn(EDGE, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${DBG}`, `--user-data-dir=${prof}`, "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, ms = 20000) { const t0 = Date.now(); for (;;) { try { const v = await fn(); if (v) return v; } catch {} if (Date.now() - t0 > ms) throw new Error("timeout"); await sleep(200); } }
const EXPR = `(async () => {
  const R = await import('./js/rank-engine.js'), S = await import('./js/rank-share.js');
  const cos = [['00126380','삼성전자',153628246,0],['00164779','SK하이닉스',177950000,0],['S3e4295b28f','삼성물산',122960000,1],['00159193','한국전력',93170000,0]];
  const mk = (i, longNames) => { const c = cos[i % 4]; return { nickname: longNames && i === 2 ? '아주아주아주긴친구별명입니다정말로길어요이름이' : '친구' + (i + 1), company: { id: c[0], name: longNames && i === 3 ? '주식회사 매우매우긴회사이름을가진한국테스트산업개발' : c[1], legal: c[1], pay: c[2] + i * 1000, src: c[3], year: 2025, ind: 1, hold: 0 } }; };
  const mkN = (n, long) => R.calculateRanking(Array.from({ length: n }, (_, i) => mk(i, long)));
  const withMissing = R.calculateRanking([mk(0), mk(1), { nickname: '자료없음친구', company: { id: '00999999', name: '자료 없는 회사', legal: 'x', pay: null, src: null, year: null, ind: -1, hold: 0 } }]);
  const url = location.origin + location.pathname;
  const toUrl = r => S.renderRankingCanvas(r, { pageUrl: url, now: new Date('2026-11-07') }).toDataURL('image/png');
  return JSON.stringify({ two: toUrl(mkN(2)), ten: toUrl(mkN(10, true)), missing: toUrl(withMissing) });
})()`;
try {
  const tgt = await until(async () => (await (await fetch(`http://127.0.0.1:${DBG}/json`)).json()).find(t => t.type === "page"));
  const ws = new WebSocket(tgt.webSocketDebuggerUrl); await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const wait = new Map(), events = [];
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d); wait.delete(d.id); } else events.push(d.method); };
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; wait.set(i, d => (d.error ? rej(new Error(d.error.message)) : res(d.result))); ws.send(JSON.stringify({ id: i, method, params })); });
  await send("Page.enable"); await send("Page.navigate", { url: `http://127.0.0.1:${port}/rank.html` });
  await until(() => events.includes("Page.loadEventFired")); await sleep(1500);
  const r = await send("Runtime.evaluate", { expression: EXPR, awaitPromise: true, returnByValue: true });
  const o = JSON.parse(r.result.value);
  for (const [k, v] of Object.entries(o)) writeFileSync(join(out, `share-${k}.png`), Buffer.from(v.split(",")[1], "base64"));
  console.log("saved", Object.keys(o).join(","));
  ws.close();
} finally {
  try { execFileSync("taskkill", ["/F", "/T", "/PID", String(proc.pid)], { stdio: "ignore" }); } catch {}
  await sleep(500); try { rmSync(prof, { recursive: true, force: true }); } catch {}
}
