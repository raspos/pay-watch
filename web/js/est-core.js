// 근속 구간별 추정 — 순수 로직(DOM 없음, node --test 로 검증). 이 파일은 코드만 두며 데이터는 포함하지 않는다.
// 값은 연구 결과(만원 정수, 연환산 집단 평균급여)를 그대로 쓴다. 결과가 없는 값(null)에는 어떤 금액도 만들지 않는다.
export const BINS = ["1년미만", "1~3년미만", "3~5년미만", "5~10년미만", "10년이상"];
export const BIN_LABEL = ["1년 미만", "1~3년", "3~5년", "5~10년", "10년 이상"];
export const DEFAULT_BIN = 3;                  // 5~10년: 검색 직후 바로 숫자가 보이도록 미리 선택하는 구간
export const WIDE = 0.30;                      // 설명용 경고 기준(통계적으로 검증된 신뢰도 등급이 아님)
export const MARKET = { Y: "유가증권시장", K: "코스닥", N: "코넥스", E: "기타(비상장·외감)" };

// 만원 정수 → "1억 1,624만"
export function fmtEok(v) {
  if (v == null || !Number.isFinite(v)) return null;
  const n = Math.round(v), eok = Math.floor(n / 10000), man = n % 10000;
  return (eok ? `${eok}억${man ? ` ${man.toLocaleString("ko-KR")}만` : ""}` : `${man.toLocaleString("ko-KR")}만`);
}
export function fmtRange(r) {
  if (!r) return null;
  const [lo, hi] = r; return `${fmtEok(lo)} ~ ${fmtEok(hi)}원`;
}
export const relWidth = r => (r ? (r[1] - r[0]) / ((r[1] + r[0]) / 2) : null);
export const isWide = r => (r ? relWidth(r) > WIDE : false);

// ---- 기업별 표시 방식(범위를 표시해도 되는 기업만). 새 임계값 없음 ----
// A 범위 / B 범위 + 짧은 민감도 안내 / C 공시 평균급여만(범위 없음) / D 급여 값 없음(이유만)
export const gradeOf = rec => (rec && ["A", "B", "C", "D"].includes(rec.g) ? rec.g : "D");
export const displayMode = rec => ({ A: "range", B: "range", C: "pay", D: "none" })[gradeOf(rec)];

// ---- 상태·사유 ----
const REASON = {
  THRESHOLD_BAND: "공시 평균급여가 같은 산업의 10년 이상 구간 평균보다 높아(1.25~2.0배) 산업 임금곡선을 이 기업에 적용하는 가정의 영향이 큽니다.",
  EXTRAPOLATION_BEYOND_ALL_THRESHOLDS: "공시 평균급여가 같은 산업의 10년 이상 구간 평균의 2배를 넘어, 산업 임금곡선을 적용하는 가정이 가장 큰 외삽입니다.",
  PAY_CONSISTENCY: "공시 자료의 행별 평균급여와 급여총액÷직원 수가 5% 넘게 달라 급여 수치의 정합성이 낮습니다.",
  MAPPING_RISK_NAME: "지주회사·홀딩스 등은 산업 분류가 실제 사업과 달라 산업 임금곡선이 맞지 않을 수 있습니다.",
  WIDE_RANGE: "인력 구성 가정에 따른 범위의 폭이 큽니다.",
  FEW_SCENARIOS: "기업 평균근속과 양립하는 가정이 적어 결과가 가정 선택에 민감합니다.",
  NO_INDUSTRY_CODE: "기업개황에 산업코드가 없어 산업 임금통계와 연결하지 못했습니다.",
  INDUSTRY_CODE_INVALID: "산업코드가 올바르지 않아 산업 임금통계와 연결하지 못했습니다.",
  NO_OFFICIAL_STAT_FOR_INDUSTRY: "해당 산업의 근속 구간별 공식 임금통계가 없습니다.",
  "MATH_INFEASIBLE:M10_RANGE_EMPTY": "기업 평균근속이 산업의 장기근속 통계 범위보다 길어, 정해 둔 인력 구성 가정에서 계산할 수 없습니다.",
  MAPPING_SUSPECT_LEVEL: "공시 평균급여가 산업 평균과 지나치게 달라(4배 초과 또는 0.25배 미만) 산업 매핑·급여 정의 오류 가능성이 커서 추정하지 않았습니다.",
  TENURE_IMPLAUSIBLE: "공시된 평균근속연수가 비현실적이어서(45년 초과) 자료 오류로 보고 추정하지 않았습니다.",
};
export const reasonText = code => REASON[String(code).replace(/\(.*$/, "")] ?? REASON[code] ?? "계산 기준을 충족하지 못했습니다.";
export const STATUS_LABEL = { CALCULATED: "계산됨", SENSITIVE: "가정·기준에 민감", INVALID: "추정하지 않음", INSUFFICIENT: "자료 부족" };

// 선택 구간의 결과. 추정 불가이면 금액 필드를 만들지 않는다.
export function resolveBin(rec, bin) {
  if (!canEstimate(rec)) return { kind: "na" };
  const base = rec.b[bin], exp = rec.x ? rec.x[bin] : null;
  return { kind: "range", base, exp, held: !!(rec.h ?? rec.x == null), baseWide: isWide(base), expWide: isWide(exp), baseW: relWidth(base), expW: relWidth(exp) };
}
export const canEstimate = rec => !!(rec && rec.b && (rec.g === undefined || displayMode(rec) === "range"));   // 공개 데이터는 A·B 기업만 담고 등급 필드가 없다(범위가 있으면 표시 대상)

// ---- 그래프 좌표: 5개 구간별 막대(구간 사이를 잇지 않는다), 세로축은 0에서 시작하지 않을 수 있다 ----
function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw)), f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}
export function chartModel(rec, bin = null, { W = 640, H = 320, m = { l: 78, r: 14, t: 16, b: 46 } } = {}) {
  if (!canEstimate(rec)) return null;
  const vals = rec.b.flat().concat(rec.x ? rec.x.flat() : [], rec.a != null ? [rec.a] : []);
  const lo = Math.min(...vals), hi = Math.max(...vals), step = niceStep((hi - lo) / 5 || 100);
  const ymin = Math.max(0, Math.floor((lo * 0.9) / step) * step), ymax = Math.ceil((hi * 1.05) / step) * step;
  const y = v => m.t + (H - m.t - m.b) * (1 - (v - ymin) / (ymax - ymin)), cw = (W - m.l - m.r) / 5, bw = Math.min(46, cw * 0.5);
  const x = i => m.l + cw * (i + 0.5);
  const bars = BINS.map((b, i) => ({ i, x: x(i), bw, base: rec.b[i], exp: rec.x ? rec.x[i] : null, yb: [y(rec.b[i][1]), y(rec.b[i][0])], ye: rec.x ? [y(rec.x[i][1]), y(rec.x[i][0])] : null, selected: i === bin }));
  const ticks = []; for (let v = ymin; v <= ymax + 1e-9; v += step) ticks.push({ v, y: y(v) });
  return { W, H, m, ymin, ymax, bars, ticks, avgY: rec.a != null ? y(rec.a) : null, zeroBased: ymin === 0 };
}

// ---- URL 상태 ----
export function parseQuery(search) {
  const q = new URLSearchParams(search || "");
  const c = q.get("c"), b = q.get("b");
  return { code: c && /^\d{8}$/.test(c) ? c : null, bin: b != null && /^[0-4]$/.test(b) ? Number(b) : null };   // bin 이 없으면 화면에서 DEFAULT_BIN 을 쓴다
}
export const buildQuery = (code, bin) => (code ? `?c=${code}${bin != null ? `&b=${bin}` : ""}` : "");
export const shardOf = (code, n = 64) => Number(code) % n;
