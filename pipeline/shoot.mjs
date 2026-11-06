// 로컬 미리보기 화면 캡처 + 가로 넘침 측정(문서·점검용). 사용: node pipeline/shoot.mjs <before|after> [포트=8791] [이름=경로 ...]
// 127.0.0.1 의 로컬 미리보기 서버만 대상으로 한다(pipeline/serve_preview.py). headless Edge 를 개발자 도구 프로토콜(127.0.0.1 전용 포트)로 조작해
// 데스크톱 1280x900, 모바일 375x812(터치·모바일 에뮬레이션) 전체 페이지를 찍고, 각 화면의 scrollWidth 와 innerWidth 를 기록한다.
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const EDGE = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const [tag = "after", port = "8791", ...extra] = process.argv.slice(2);
const PAGES = { index: "index.html", "exp-search": "exp.html", "exp-result": "exp.html?c=00126380", company: "company.html?corp=00126380", compare: "compare.html", lab: "lab.html", methodology: "methodology.html" };
for (const e of extra) { const i = e.indexOf("="); PAGES[e.slice(0, i)] = e.slice(i + 1); }
const SIZES = { desktop: [1280, 900, false], mobile: [375, 812, true] };
const out = fileURLToPath(new URL("../docs/screenshots/phase13/" + tag, import.meta.url)); mkdirSync(out, { recursive: true });

const prof = mkdtempSync(join(tmpdir(), "shoot-")), DBG = 9333;
const proc = spawn(EDGE, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${DBG}`, `--user-data-dir=${prof}`, "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(fn, ms = 20000) { const t0 = Date.now(); for (;;) { try { const v = await fn(); if (v) return v; } catch {} if (Date.now() - t0 > ms) throw new Error("timeout"); await sleep(200); } }

try {
  const tgt = await until(async () => (await (await fetch(`http://127.0.0.1:${DBG}/json`)).json()).find(t => t.type === "page"));
  const ws = new WebSocket(tgt.webSocketDebuggerUrl); await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const wait = new Map(), events = [];
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d); wait.delete(d.id); } else events.push(d.method); };
  const send = (method, params = {}) => new Promise((res, rej) => { const i = ++id; wait.set(i, d => (d.error ? rej(new Error(method + ": " + d.error.message)) : res(d.result))); ws.send(JSON.stringify({ id: i, method, params })); });
  await send("Page.enable");
  const report = [];
  for (const [name, path] of Object.entries(PAGES)) for (const [dev, [w, h, mobile]] of Object.entries(SIZES)) {
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile });
    events.length = 0; await send("Page.navigate", { url: `http://127.0.0.1:${port}/${path}` });
    await until(() => events.includes("Page.loadEventFired")); await sleep(1800);
    const ev = await send("Runtime.evaluate", { expression: "JSON.stringify({sw:document.documentElement.scrollWidth,iw:innerWidth})", returnByValue: true });
    const m = JSON.parse(ev.result.value);
    const lm = await send("Page.getLayoutMetrics"); const H = Math.min(Math.ceil(lm.cssContentSize.height), 3200);
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: w, height: Math.max(H, h), scale: 1 } });
    writeFileSync(join(out, `${name}-${dev}.png`), Buffer.from(shot.data, "base64"));
    report.push({ page: name, dev, scrollWidth: m.sw, innerWidth: m.iw, overflow: m.sw > m.iw });
  }
  console.table(report);
  writeFileSync(join(out, "overflow.json"), JSON.stringify(report, null, 1));
  ws.close();
} finally {
  try { execFileSync("taskkill", ["/F", "/T", "/PID", String(proc.pid)], { stdio: "ignore" }); } catch {}
  await sleep(500); try { rmSync(prof, { recursive: true, force: true }); } catch {}
}
