// 사이트 설정. 정정·제보 연락처는 실제 채널이 확정되기 전까지 null 로 둔다(가짜 이메일·접수처를 만들지 않는다). null 이면 푸터에 표시하지 않는다.
export const CONTACT = null;     // 예: { label: "정정·제보", href: "mailto:..." } — 배포 전 사용자가 확정

// 조회수 카운터 서버 주소(cloudflare/views-worker.js 배포 주소). null 이면 조회수를 표시하지 않는다. 예: "https://pay-watch-views.<계정>.workers.dev"
export const VIEWS_URL = null;
