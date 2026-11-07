import { chrome, esc, fmtInt, getMeta } from "./common.js?v=1fc405ae56";

chrome("methodology.html");
const ym = s => s === "9999-12" ? "이후" : s.replace("-", ".");
getMeta().then(m => {
  document.getElementById("ver").textContent = `방법론 버전 ${m.methodology_version}`;
  document.getElementById("base").textContent = m.base_month;
  document.querySelector(".range").textContent = `${m.months[0]}~${m.months[m.months.length - 1]}`;
  document.getElementById("rates").innerHTML = m.rates.map(r => `<tr><td>${ym(r.from)} ~ ${ym(r.to)}</td><td class="num">${(r.total * 100).toFixed(1)}%${r.verified ? "" : " <span class='tag'>법령 원문 대조 전</span>"}</td></tr>`).join("");
  document.getElementById("caps").innerHTML = m.caps.map(c => `<tr><td>${ym(c.from)} ~ ${ym(c.to)}</td><td class="num">${fmtInt(c.upper)}원</td></tr>`).join("");
}).catch(() => { document.getElementById("rates").innerHTML = `<tr><td colspan="2">표를 불러오지 못했습니다.</td></tr>`; });
