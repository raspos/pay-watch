// 대표 평균연봉 소스 선택(순수 로직). 우선순위: ① 유효한 DART 공시 평균급여 → ② 사람인 추정 평균연봉 → ③ 자료 없음.
// DART 가 없거나(공시 없음) 품질 문제로 보류(일관성 미확인·공시 값 확인 중)인 경우에만 사람인을 쓴다. 원본값은 소스별로 따로 두며 서로 덮어쓰지 않는다.
// 사람인 값은 공시값이 아닌 '추정'이며, 표시연도는 원천자료의 관측연도와 구분한다. 국민연금 보험료 역산값은 소스가 아니다(참고용 '추정'으로만 표시).
export const SOURCES = [
  { id: "dart", label: "DART 공시", estimate: false,
    get: c => (c.dart && c.dart.level === "ok" && c.dart.avg != null ? { value: c.dart.avg, year: c.dart.fy, href: c.dart.src, scope: "기업 전체 평균" } : null) },
  { id: "saramin", label: "사람인 추정", estimate: true,
    get: c => (c.saramin && c.saramin.v != null ? { value: c.saramin.v, year: c.saramin.y, scope: "기업 평균(사람인 통계 추정)" } : null) },
];

/** c: 기업 레코드({dart, hold?, saramin?}). 반환: {kind:"value", source, label, estimate, value, year, reason, ...} | {kind:"hold", why} | {kind:"none"} */
export function pickRepresentative(c, sources = SOURCES) {
  const dartHeld = !!(c && (c.hold || (c.dart && c.dart.level !== "ok")));
  for (const s of sources) {
    const v = c ? s.get(c) : null;
    if (v) return { kind: "value", source: s.id, label: s.label, estimate: s.estimate, reason: s.id === "dart" ? "dart_valid" : (dartHeld ? "dart_held_quality" : "dart_missing"), ...v };
  }
  if (c && c.hold) return { kind: "hold", why: "공시 평균급여 자료를 확인 중입니다." };
  if (c && c.dart && c.dart.level !== "ok") return { kind: "hold", why: "공시 급여의 일관성이 확인되지 않아 대표 값으로 쓰지 않았습니다." };
  return { kind: "none" };
}

/** 화면에 숫자로 보여도 되는 DART 평균급여(원). 일관성 검증을 통과(level=ok)한 값만 반환하고, 보류·확인 중·없음이면 null. 결과 화면·그래프·사실표·비교는 모두 이 값만 쓴다. */
export function visibleDartAvg(c) {
  return c && c.dart && c.dart.level === "ok" && c.dart.avg != null ? c.dart.avg : null;
}
