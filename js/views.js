// 방문 통계: GoatCounter(쿠키 없음·개인 식별 정보 수집 없음). 사이트 코드는 site-config.js 의 GOATCOUNTER_CODE — null 이면 아무것도 하지 않는다(집계도, 표시도 없음).
// 집계: GoatCounter 공식 스크립트(count.js)를 불러온다. 표시: GoatCounter 대시보드에서 "Allow adding visitor counts on your website" 를 켜면 공개 카운터(TOTAL.json)를 읽어 푸터에 누적 조회수를 보여준다. 읽지 못하면 표시하지 않는다.
export const CODE_RE = /^[a-z0-9][a-z0-9-]{1,29}$/;
export const counterUrl = code => (CODE_RE.test(code || "") ? `https://${code}.goatcounter.com/counter/TOTAL.json` : null);

export function loadGoatCounter(code, doc = document) {
  if (!CODE_RE.test(code || "") || doc.querySelector("script[data-goatcounter]")) return false;
  const s = doc.createElement("script");
  s.async = true; s.src = "https://gc.zgo.at/count.js"; s.setAttribute("data-goatcounter", `https://${code}.goatcounter.com/count`);
  doc.head.appendChild(s);
  return true;
}

/** 공개 카운터의 누적 조회수를 푸터 요소에 표시. 형식: {count:"12 345"} (공백·쉼표는 무시하고 숫자만 읽는다). */
export async function showTotal({ code, el, fetchFn = (typeof fetch === "function" ? fetch : null) }) {
  const url = counterUrl(code);
  if (!url || !el || !fetchFn) return null;
  try {
    const r = await fetchFn(url, { cache: "no-store" });
    if (!r.ok) return null;
    const n = parseInt(String((await r.json()).count ?? "").replace(/\D/g, ""), 10);
    if (!Number.isFinite(n)) return null;
    el.textContent = `조회수 누적 ${n.toLocaleString("ko-KR")}`; el.hidden = false;
    return n;
  } catch { return null; }
}
