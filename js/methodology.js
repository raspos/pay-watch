import { chrome, esc, fmtInt, getMeta } from "./common.js?v=e5fe82c4d7";
import { GOATCOUNTER_CODE } from "./site-config.js?v=e5fe82c4d7";

chrome("methodology.html");
const ym = s => s === "9999-12" ? "이후" : s.replace("-", ".");
getMeta().then(m => {
  document.getElementById("ver").textContent = `방법론 버전 ${m.methodology_version}`;
  document.getElementById("base").textContent = m.base_month;
  document.querySelector(".range").textContent = `${m.months[0]}~${m.months[m.months.length - 1]}`;
  document.getElementById("rates").innerHTML = m.rates.map(r => `<tr><td>${ym(r.from)} ~ ${ym(r.to)}</td><td class="num">${(r.total * 100).toFixed(1)}%${r.verified ? "" : " <span class='tag'>법령 원문 대조 전</span>"}</td></tr>`).join("");
  document.getElementById("caps").innerHTML = m.caps.map(c => `<tr><td>${ym(c.from)} ~ ${ym(c.to)}</td><td class="num">${fmtInt(c.upper)}원</td></tr>`).join("");
}).catch(() => { document.getElementById("rates").innerHTML = `<tr><td colspan="2">표를 불러오지 못했습니다.</td></tr>`; });
if (GOATCOUNTER_CODE) {                                       // 방문 통계를 쓰는 경우에만 안내(쿠키·개인 식별 정보 없음)
  const last = [...document.querySelectorAll("details.qa")].pop();
  if (last) last.insertAdjacentHTML("beforeend", '<p class="disclaimer">방문 통계: 방문 횟수 집계에 GoatCounter(쿠키 없음, 개인 식별 정보 수집 없음)를 사용합니다.</p>');
}
