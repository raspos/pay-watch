// 조회수(푸터): BOK워치의 방식을 옮겼다 — 같은 브라우저 세션에서는 한 번만 올리고(POST), 이후에는 읽기만(GET) 한다. 카운터 서버가 없거나 실패하면 아무것도 표시하지 않는다.
// 카운터 서버 주소는 site-config.js 의 VIEWS_URL(cloudflare/views-worker.js 를 배포한 주소). 방문 횟수만 세며 IP·식별 정보를 보내거나 저장하지 않는다.
export async function showViews({ url, el, fetchFn = (typeof fetch === "function" ? fetch : null), storage = null, key = "paywatch.counted" }) {
  if (!url || !el || !fetchFn) return null;
  let counted = false;
  try { counted = !!storage && storage.getItem(key) === "1"; } catch { /* 사생활 보호 모드 등 */ }
  try {
    const r = await fetchFn(url, { method: counted ? "GET" : "POST", cache: "no-store" });
    if (!r.ok) return null;
    const v = await r.json();
    if (typeof v.total !== "number" || typeof v.today !== "number") return null;
    try { storage && storage.setItem(key, "1"); } catch { /* 무시 */ }
    el.textContent = `조회수 오늘 ${v.today.toLocaleString("ko-KR")} · 누적 ${v.total.toLocaleString("ko-KR")}`;
    el.hidden = false;
    return v;
  } catch { return null; }
}
