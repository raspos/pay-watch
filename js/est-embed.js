// 근속 구간별 집단 평균급여 추정 영역 로더(회사 결과 화면 company.html 전용). 추정 데이터가 있는 기업(A·B 2,138곳)에만 영역을 그리고, 없으면 아무것도 렌더링하지 않는다.
import { mountEstimate } from "./est-section.js?v=080a125729";

const go = () => {
  const slot = document.getElementById("exp-slot"), code = new URLSearchParams(location.search).get("corp"), r = window.__pwResult;
  if (!slot || !/^\d{8}$/.test(code || "") || !r || r.code !== code) return;                        // 결과 화면이 표시값을 확정한 뒤에만(보류된 공시 평균이 그래프에 쓰이지 않게)
  mountEstimate(slot, code, { dartAvgMan: r.dartAvg != null ? r.dartAvg / 10000 : null });
};
window.addEventListener("pw:result", go);
go();
