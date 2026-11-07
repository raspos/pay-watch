// PAY워치 조회수 카운터(Cloudflare Worker + KV). BOK워치 functions/api/views.js 를 GitHub Pages 용 별도 Worker 로 옮겼다(Pages 는 정적 호스팅이라 서버 코드를 못 돌린다).
// 배포(사용자 Cloudflare 계정에서): ① KV 네임스페이스 생성 ② Worker 생성 후 이 파일을 붙여넣기 ③ Settings → Bindings 에서 KV 를 변수 이름 VIEWS 로 연결 ④ Worker 주소(예 https://pay-watch-views.<계정>.workers.dev)를 web/js/site-config.js 의 VIEWS_URL 에 적고 재배포.
// GET → {total, today}, POST → 1 올린 뒤 {total, today}. 허용 출처는 ALLOW 의 사이트뿐이다. 값은 총 방문 수와 날짜별 수만 저장하고 IP·UA·식별자는 저장하지 않는다. KV 는 원자적 증가가 아니라 동시 요청 일부가 빠질 수 있다(대략치).
const ALLOW = ["https://raspos.github.io"];
const json = (obj, status, origin) => new Response(JSON.stringify(obj), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", "access-control-allow-origin": origin, "vary": "origin" },
});

export default {
  async fetch(request, env) {
    const origin = request.headers.get("origin") || "";
    const allowed = ALLOW.includes(origin) ? origin : ALLOW[0];
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: { "access-control-allow-origin": allowed, "access-control-allow-methods": "GET, POST, OPTIONS", "access-control-max-age": "86400", vary: "origin" } });
    if (!ALLOW.includes(origin) && request.method === "POST") return json({ error: "origin" }, 403, allowed);      // 다른 사이트에서 올리지 못하게
    if (!env.VIEWS) return json({ error: "VIEWS 연결 없음" }, 503, allowed);
    if (!["GET", "POST"].includes(request.method)) return json({ error: "method" }, 405, allowed);
    const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);       // KST 날짜
    const dayKey = `d:${today}`;
    let [total, day] = await Promise.all([env.VIEWS.get("total"), env.VIEWS.get(dayKey)]);
    total = parseInt(total || "0", 10); day = parseInt(day || "0", 10);
    if (request.method === "POST") {
      total += 1; day += 1;
      await Promise.all([env.VIEWS.put("total", String(total)), env.VIEWS.put(dayKey, String(day), { expirationTtl: 60 * 60 * 24 * 40 })]);
    }
    return json({ total, today: day }, 200, allowed);
  },
};
