// PAY RANK 공유 엔진: 1080px 세로형 PNG(Canvas 2D, 외부 라이브러리·외부 폰트 없음), 공유 링크(기업 식별자만, 별명은 명시적 선택 시에만), 링크 복사, 모바일 네이티브 공유, 임베드 코드.
// pay-rank/js/share.js 를 ES 모듈로 옮겼고, 친구 10명까지 높이를 동적으로 늘리며 긴 이름은 잘라내지 않고 줄바꿈·글자 축소로 모두 보이게 했다.
import { DISCLAIMER, MIX_NOTE } from "./rank-engine.js?v=1f6a6aec9c";

export const ID_RE = /^(\d{8}|S[0-9a-f]{10})$/;
export const W = 1080, PAD = 72;
const FONT = "'Pretendard','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif";

// ---- 링크 ----
/** 공유 URL: 기본은 기업 식별자만(?c=id,id,…). includeNicknames 가 true 일 때만 별명(?n=)을 넣는다. 외부 서버에 저장하지 않는다. */
export function generateShareUrl(friends, includeNicknames = false, loc = (typeof location !== "undefined" ? location : { origin: "https://example.com", pathname: "/rank.html" })) {
  const base = loc.origin + loc.pathname;
  const ids = friends.filter(f => f.company && ID_RE.test(f.company.id)).map(f => f.company.id);
  if (!ids.length) return base;
  let url = `${base}?c=${ids.join(",")}`;
  if (includeNicknames) url += `&n=${friends.filter(f => f.company && ID_RE.test(f.company.id)).map(f => encodeURIComponent(String(f.nickname || "").trim().slice(0, 20))).join(",")}`;
  return url;
}

/** 검색 문자열 → {ids, nicks, embed, add}. 형식이 올바른 식별자만 최대 10개. */
export function parseShareParams(search) {
  const q = new URLSearchParams(search || "");
  const ids = (q.get("c") || "").split(",").map(s => s.trim()).filter(s => ID_RE.test(s)).slice(0, 10);
  const nicks = q.get("n") ? q.get("n").split(",").map(s => { try { return decodeURIComponent(s).slice(0, 20); } catch { return ""; } }) : [];
  const add = q.get("add") && ID_RE.test(q.get("add")) ? q.get("add") : null;
  return { ids, nicks, embed: q.get("embed") === "1", add };
}

export function embedUrl(shareUrl) { return shareUrl + (shareUrl.includes("?") ? "&" : "?") + "embed=1"; }
export function generateEmbedCode(shareUrl) {
  return `<iframe src="${embedUrl(shareUrl)}" width="100%" height="520" frameborder="0" loading="lazy" style="border:1px solid #e3e5e8;border-radius:12px;max-width:520px" title="PAY워치 내 친구들 연봉 랭킹"></iframe>`;
}
export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(text); return true; }
    const t = document.createElement("textarea"); t.value = text; t.style.cssText = "position:fixed;opacity:0"; document.body.appendChild(t); t.select(); const ok = document.execCommand("copy"); t.remove(); return ok;
  } catch { return false; }
}
export async function nativeShare(title, text, url) {
  if (!navigator.share) return false;
  try { await navigator.share({ title, text: `${text}\n(※ ${DISCLAIMER})`, url }); return true; } catch (e) { return e && e.name === "AbortError" ? false : false; }
}

// ---- 이미지 ----
/** 글자를 maxWidth 안에서 최대 maxLines 줄로 나눈다(글자 단위). 넘치면 마지막 줄만 말줄임. measure(text)=폭 */
export function wrapLines(measure, text, maxWidth, maxLines) {
  const chars = [...String(text || "")], lines = [];
  let cur = "";
  for (const ch of chars) {
    if (measure(cur + ch) <= maxWidth || !cur) cur += ch; else { lines.push(cur); cur = ch; }
  }
  if (cur) lines.push(cur);
  if (lines.length <= maxLines) return { lines, truncated: false };
  let last = lines.slice(maxLines - 1).join("");
  while (last.length > 1 && measure(last + "…") > maxWidth) last = last.slice(0, -1);
  return { lines: [...lines.slice(0, maxLines - 1), last + "…"], truncated: true };
}

/** 긴 글자는 먼저 글자 크기를 줄여(최소 minSize) 줄 수를 줄이고, 그래도 안 되면 줄바꿈한다. 어떤 경우에도 잘라내지 않는다(마지막 수단 말줄임은 maxLines 초과 때만). */
function fit(ctx, text, weight, size, minSize, maxWidth, maxLines) {
  for (let s = size; s >= minSize; s -= 2) {
    ctx.font = `${weight} ${s}px ${FONT}`;
    const r = wrapLines(t => ctx.measureText(t).width, text, maxWidth, 1);
    if (!r.truncated && r.lines.length <= 1) return { size: s, lines: r.lines };
  }
  ctx.font = `${weight} ${minSize}px ${FONT}`;
  const r = wrapLines(t => ctx.measureText(t).width, text, maxWidth, maxLines);
  return { size: minSize, lines: r.lines };
}

/** 결과(PayRank calculateRanking) → 캔버스. 높이는 친구 수·줄바꿈에 맞춰 동적으로 정해진다. */
export function renderRankingCanvas(result, opts = {}) {
  const { pageUrl = "", now = new Date(), includeNickname = true } = opts;
  const canvas = document.createElement("canvas"), ctx = canvas.getContext("2d");
  canvas.width = W;
  const colRank = 130, colRight = 340, midW = W - PAD * 2 - colRank - colRight - 24;
  // 1) 레이아웃 계산(높이)
  canvas.height = 4000;                                                         // 측정용 임시 높이
  const rows = result.ranked.map(r => {
    const nick = fit(ctx, includeNickname ? r.nickname : "친구", "800", 40, 28, midW, 2), comp = fit(ctx, r.companyName, "500", 30, 24, midW, 2);
    const pay = fit(ctx, r.formatted, "800", 50, 30, colRight, 1);
    const h = Math.max(150, 28 + nick.lines.length * 46 + comp.lines.length * 38 + 28);
    return { r, nick, comp, pay, h };
  });
  const un = result.unranked.map(u => ({ u, nick: fit(ctx, u.nickname, "700", 28, 22, W - PAD * 2 - 380, 2), comp: fit(ctx, u.companyName, "500", 26, 22, 360, 2) }));
  const noteLines = [];
  const notes = [DISCLAIMER, ...(result.mixedSources ? [MIX_NOTE] : [])];
  ctx.font = `600 26px ${FONT}`;
  notes.forEach(n => noteLines.push(...wrapLines(t => ctx.measureText(t).width, n, W - PAD * 2, 3).lines));
  const srcText = sourceLine(result);
  ctx.font = `500 22px ${FONT}`;
  const srcLines = wrapLines(t => ctx.measureText(t).width, srcText, W - PAD * 2, 3).lines;
  let height = 300 + rows.reduce((s, x) => s + x.h, 0) + (un.length ? 90 + un.length * 84 : 0) + 40 + noteLines.length * 38 + srcLines.length * 32 + 150;
  height = Math.max(height, 1100);
  canvas.height = height;
  // 2) 그리기
  ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, W, height);
  ctx.fillStyle = "#1a55e6"; ctx.fillRect(0, 0, W, 14);
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#1a55e6"; ctx.font = `800 30px ${FONT}`; ctx.fillText("PAY WATCH / PAY RANK", PAD, 90);
  ctx.fillStyle = "#111418"; ctx.font = `800 66px ${FONT}`; ctx.fillText("내 친구들 연봉 랭킹", PAD, 176);
  ctx.fillStyle = "#5a606a"; ctx.font = `500 30px ${FONT}`; ctx.fillText("우리 중 누가 제일 잘 버는 회사에 다닐까?", PAD, 228);
  let y = 270;
  ctx.strokeStyle = "#111418"; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
  rows.forEach(({ r, nick, comp, pay, h }) => {
    const top = y, mid = PAD + colRank;
    ctx.fillStyle = r.rank <= 3 ? "#1a55e6" : "#111418"; ctx.font = `800 46px ${FONT}`; ctx.textAlign = "left";
    ctx.fillText(`${r.rank}위`, PAD, top + 72);
    let ty = top + 30 + 36;
    ctx.fillStyle = "#111418"; ctx.font = `800 ${nick.size}px ${FONT}`;
    nick.lines.forEach(l => { ctx.fillText(l, mid, ty); ty += 46; });
    ctx.fillStyle = "#5a606a"; ctx.font = `500 ${comp.size}px ${FONT}`;
    comp.lines.forEach(l => { ctx.fillText(l, mid, ty); ty += 38; });
    ctx.textAlign = "right";
    ctx.fillStyle = r.rank <= 3 ? "#1a55e6" : "#111418"; ctx.font = `800 ${pay.size}px ${FONT}`; ctx.fillText(r.formatted, W - PAD, top + 72);
    ctx.fillStyle = "#5a606a"; ctx.font = `500 24px ${FONT}`; ctx.fillText(`${r.source}${r.year ? ` · ${r.year}년` : ""}`, W - PAD, top + 112);
    ctx.textAlign = "left";
    y += h;
    ctx.strokeStyle = "#e3e5e8"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - PAD, y); ctx.stroke();
  });
  if (un.length) {
    y += 60; ctx.fillStyle = "#5a606a"; ctx.font = `700 26px ${FONT}`; ctx.fillText("연봉 자료 없음 (순위 제외)", PAD, y); y += 24;
    un.forEach(({ u, nick, comp }) => {
      ctx.fillStyle = "#111418"; ctx.font = `700 ${nick.size}px ${FONT}`; nick.lines.forEach((l, i) => ctx.fillText(l, PAD, y + 44 + i * 32));
      ctx.fillStyle = "#5a606a"; ctx.font = `500 ${comp.size}px ${FONT}`; ctx.textAlign = "right"; comp.lines.forEach((l, i) => ctx.fillText(l, W - PAD, y + 44 + i * 30)); ctx.textAlign = "left";
      y += 84;
    });
  }
  y += 56;
  ctx.fillStyle = "#111418"; ctx.font = `600 26px ${FONT}`;
  noteLines.forEach(l => { ctx.fillText(l, PAD, y); y += 38; });
  y += 4; ctx.fillStyle = "#5a606a"; ctx.font = `500 22px ${FONT}`;
  srcLines.forEach(l => { ctx.fillText(l, PAD, y); y += 32; });
  ctx.fillStyle = "#1a55e6"; ctx.font = `700 24px ${FONT}`; ctx.fillText(pageUrl ? pageUrl.replace(/^https?:\/\//, "").replace(/\?.*$/, "") : "PAY WATCH", PAD, height - 52);
  ctx.fillStyle = "#5a606a"; ctx.font = `500 22px ${FONT}`; ctx.textAlign = "right";
  ctx.fillText(`${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")} 생성`, W - PAD, height - 52); ctx.textAlign = "left";
  return canvas;
}

export function sourceLine(result) {
  const s = new Set(result.ranked.map(r => r.src)), parts = [];
  if (s.has(0)) parts.push("DART 사업보고서 공시");
  if (s.has(1)) parts.push("사람인 추정(공시값 아님)");
  return `출처: ${parts.join(", ") || "-"}${result.years.length ? ` · 기준·표시연도 ${result.years.join(", ")}` : ""}`;
}

export function downloadRankingImage(result, opts = {}) {
  const canvas = renderRankingCanvas(result, opts);
  return new Promise((resolve, reject) => canvas.toBlob(blob => {
    if (!blob) return reject(new Error("이미지 생성 실패"));
    const a = document.createElement("a"), u = URL.createObjectURL(blob);
    a.href = u; a.download = `pay-rank-${new Date().toISOString().slice(0, 10)}.png`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 4000); resolve(canvas);
  }, "image/png"));
}
