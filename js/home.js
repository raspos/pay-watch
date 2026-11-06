// 메인 화면: 통합 기업 찾기(DART 법인 + 국민연금 사업장) 하나만. 순위·차트·통계는 두지 않는다.
import { chrome } from "./common.js?v=375f4d5dac";
import { mountFinder } from "./finder-ui.js?v=375f4d5dac";
import { resultHref } from "./finder-core.js?v=375f4d5dac";
import { searchTop } from "./search.js?v=375f4d5dac";

chrome("index.html");
mountFinder(document.getElementById("search"), {
  placeholder: "회사 이름을 검색하세요 (예: 삼성전자, SK하이닉스)", label: "회사 검색", autofocus: false,
  nps: async q => (await searchTop(q, 6)).list,           // 법인 결과 아래에 '국민연금 사업장'으로 따로 표시. 식별자는 사업장 id 그대로
  onPick: it => { location.href = it.kind === "wp" ? `company.html?id=${it.w.id}` : resultHref(it.e); },
});
