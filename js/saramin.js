// 사람인 평균연봉 로더(공개 빌드에 사람인 데이터가 포함된 경우에만 파일이 있다). 기업 선택 후에만 해당 샤드 하나를 불러온다.
// 값은 사람인 통계 추정(원 단위)과 표시연도다. 표시연도는 원천자료의 실제 관측연도가 아닐 수 있다(확인되지 않았으며 추측하지 않는다).
import { getJSON } from "./common.js?v=375f4d5dac";

export const SHARDS = 64;
export const shardKey = id => (/^\d{8}$/.test(id) ? Number(id) % SHARDS : parseInt(String(id).slice(1, 7), 16) % SHARDS);   // pipeline/build_saramin.py shard_of 와 같은 규칙
export async function getSaramin(id) {
  try { const sh = await getJSON(`pay/s/${shardKey(id)}.json`); return sh[id] || null; } catch { return null; }
}
