// "우리 회사보다 잘 주는 곳" 판정(순수 함수). 원칙: 같은 비교집단·같은 기준의 값끼리만, 상한 접근 값은 순위에서 제외, 공시와 추정은 섞지 않는다.
export const SHOW = 10;

// items: [[id, name, value, size, ind], ...] 값 내림차순. own: 이 회사의 값. selfIds: 이 회사 자신(제외).
export function higherThan(items, own, selfIds = [], limit = SHOW) {
  if (own === null || own === undefined) return [];
  const skip = new Set(selfIds.map(String));
  return items.filter(it => !skip.has(String(it[0])) && it[2] > own).sort((a, b) => b[2] - a[2]).slice(0, limit);
}

// 추정(국민연금) 목록을 만들 수 있는지: 이 사업장이 상한에 접근했으면 만들지 않는다(하한값끼리의 순위가 되므로).
export function npsEligibility({ est, cap, gid, capNear = 0.9 }) {
  if (gid === null || gid === undefined) return { ok: false, reason: "비교집단(같은 업종·규모 30곳 이상)이 없어 목록을 만들 수 없습니다." };
  if (est === null || est === undefined) return { ok: false, reason: "이 사업장의 추정급여가 공개 대상이 아니라 비교하지 않습니다." };
  if (cap !== null && cap !== undefined && cap >= capNear) return { ok: false, reason: "이 회사는 국민연금 기준소득월액 상한에 접근해 추정값이 하한값입니다. 하한값끼리의 순위는 실제와 다를 수 있어 목록을 만들지 않았습니다. 공시 기준 목록을 참고하세요." };
  return { ok: true, reason: null };
}

// 공시 목록: 비교집단(gid)이 있고 일관성 검증을 통과한 회사만.
export function dartEligibility(dart) {
  if (!dart) return { ok: false, reason: "이 회사는 공시 급여를 확인할 수 없어 공시 기준 목록을 만들 수 없습니다." };
  if (dart.level !== "ok") return { ok: false, reason: "공시 급여의 일관성 검증을 통과하지 못해 공시 기준 목록을 만들지 않았습니다." };
  if (!dart.pos || dart.pos.gid === null || dart.pos.gid === undefined) return { ok: false, reason: "같은 업종·규모의 공시 기업이 30곳 미만이라 공시 기준 목록을 만들 수 없습니다." };
  return { ok: true, reason: null };
}

export const diffPct = (own, v) => (own ? v / own - 1 : null);
