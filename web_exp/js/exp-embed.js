// 연구용 미리보기 전용 로더. build_preview.py 가 index.html·company.html 에만 이 스크립트를 끼워 넣는다(공개 site/ 에는 없다).
import { getJSON } from "./common.js";
import { CATEGORY_LABEL, category } from "./finder-core.js";
import { mountEstimate } from "./exp-section.js";

// 검색 결과 문구: A·B 기업은 '공시 급여 + 연구용 추정', D(공시 값 의심) 기업은 급여 자료 부족으로 표시
let GRADES = null;
getJSON("exp/index.json").then(rows => { GRADES = new Map(rows.map(r => [r[0], { g: r[3], d: r[7] }])); });
window.__pwBadge = e => {
  const x = GRADES && GRADES.get(e.code);
  if (x && (x.g === "A" || x.g === "B")) return CATEGORY_LABEL.a;
  if (x && x.g === "D" && x.d === "DOUBT") return CATEGORY_LABEL.d;
  return CATEGORY_LABEL[category(e)];
};

const go = () => {
  const slot = document.getElementById("exp-slot"), code = new URLSearchParams(location.search).get("corp");
  if (slot && /^\d{8}$/.test(code || "")) mountEstimate(slot, code, { dartOk: (window.__pwResult && window.__pwResult.code === code) ? window.__pwResult.dartOk : undefined });   // 보류된 공시값은 연구용 그래프에도 쓰지 않는다
};
window.addEventListener("pw:result", go);
go();
