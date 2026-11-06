# 배포 절차 (GitHub Pages, 수동·검증형)

현재 이 폴더는 Git 저장소가 아니며 원격 저장소·기존 Pages 설정은 확인되지 않았다. 아래는 사용자가 저장소를 정한 뒤 따를 절차다. 실제 배포는 하지 않았다.

## 구조
- **저장소(공개 가능)**: 소스(`web/`, `web_exp/`, `pipeline/`, `tests/`, `config/`, `docs/`, `.github/`)만. `site/`(약 420MB), `preview/`, `dist/`, `data/`, 사람인·통합 데이터, 내부 감사 파일은 `.gitignore` + `pipeline/guard_repo.py` 로 막는다.
- **공개 사이트 데이터**: 원자료(`data/raw` 1.5GB, DART 키)가 없는 Actions 에서는 다시 만들 수 없으므로, 로컬에서 검증한 번들을 **Release 자산**으로 올려 전달한다(Git 기록에 420MB 가 쌓이지 않는다). 번들(zip, 압축 후 수십~100MB 대)은 Release 자산당 2GiB 한도 안이다.

## 사용자가 할 일
1. GitHub 저장소 결정(새로 만들기 또는 기존 저장소 확인). Settings → Pages → Source = **GitHub Actions**. 기존 Pages 가 있으면 덮어쓰지 말고 먼저 확인.
2. **사람인 권한 확인**: 외부 게시·재배포 허락(화면 표시와 JSON 재배포 범위를 구분)을 받는다. 확인되면 `config/saramin_permission_evidence.md` 에 근거(누가·언제·어떤 범위로 허락했는지, 100자 이상)를 적고 `config/publish.yaml` 의 `saramin_permission: confirmed` 로 바꾼다. 허락이 화면 표시뿐이거나 없으면 `saramin_in_site: false` 로 두고 `build_public.py` 를 다시 실행(사람인 파일 제거, DART 만 배포).
3. 로컬: `python -I -X utf8 pipeline/build_public.py` → `python -I -X utf8 pipeline/package_site.py`(검사 통과 시 `dist/pay-watch-site-<버전>.zip` + `manifest.json`).
4. **업로드는 반드시 `python -I -X utf8 pipeline/publish_release.py dist --repo 소유자/저장소 --tag 태그 --execute` 로 한다**(웹 UI·수동 업로드는 지원하지 않음). 이 스크립트가 업로드 전에 sha256·사람인 포함 여부(zip 내용 직접 검사)·권한·저장소 공개 여부를 검증하고, 통과해야만 `manifest.json` 에 업로드 전 검증 표시를 남기고 올린다. 먼저 `--execute` 없이 실행하면 점검만 한다.
5. Actions → pay-watch-pages → Run workflow, `release_tag` 입력. 소스 검증(보호 검사·전체 JS·전체 pytest)과 번들 검증(sha256·파일 수·버전·사람인 직접 검사·공개 검사·링크 점검)이 모두 통과해야 배포된다. `release_tag` 를 비우면 검증만 한다.

## 차단 장치(종료 코드에만 의존하지 않음)
- `guard_repo.py`: 커밋 대상 파일을 직접 훑어 금지 파일(site/·사람인 데이터·내부 감사·원자료·25MB 초과)이 있으면 실패.
- `package_site.py`: 번들을 만들기 전에 site/ 에 사람인 파일이 있는지 직접 보고, 권한 설정+근거 파일이 없으면 만들지 않는다(종료 코드 2).
- `pages.yml`: 번들을 푼 뒤 파일 존재 여부를 shell 로 직접 검사하고, 이어서 `check_public.py`(종료 코드 2 포함)를 실행한다.

## Release 자산 공개 범위 (공개 저장소 주의) — 예방이 원칙, 사후 삭제는 보조
- 공개 저장소의 Release 자산은 누구나 내려받을 수 있다. 사람인 게시·재배포 권한이 확인되기 전에는 사람인 데이터가 든 번들을 **공개 저장소 Release 에 올리면 안 된다**(비공개 저장소 Release 는 가능하나 Pages 사이트는 공개이므로 배포는 여전히 권한 확인이 필요).
- **예방 통제(주)**: ① `package_site.py` 는 사람인 데이터가 있는 site/ 로는 권한 확인 전에 번들 자체를 만들지 않는다(종료 코드 2). ② `publish_release.py` 는 업로드 전 필수 검증이며 사람인이 든 번들은 권한 확인 또는 **비공개 저장소 확인**일 때만 올리고, 저장소가 공개이거나 공개 여부를 확인할 수 없으면(gh 없음 등) 차단한다(fail-closed). ③ `pages.yml` 은 실제 번들에 업로드 전 검증 표시(`preupload`)가 없으면 배포하지 않는다. 권한 미확인 동안 올릴 수 있는 번들은 `saramin_in_site: false` 로 다시 만든 사람인 없는 번들뿐이다.
- **보조(탐지) 통제**: GitHub 은 웹 UI 로 직접 올리는 업로드를 사전에 막을 방법이 없으므로, `.github/workflows/release-guard.yml` 이 그런 수동 업로드를 사후에 탐지한다. Release 게시·수정 때마다 자동 실행되어 zip 안의 파일 이름(`data/pay/`, `data/finder/sm_entities.json`)을 직접 검사(manifest 표시는 믿지 않음). 공개 저장소 + 권한 미확인이면 Release 를 초안으로 되돌리고 모든 자산을 삭제한다(`pipeline/release_guard.py`). 이 보호는 업로드 후 즉시 작동하는 사후 차단이므로, 권한 미확인 동안에는 사람인 포함 번들(`package_site.py` 가 어차피 만들지 않음)을 올리지 않는 것이 원칙이다.
- 사람인 데이터 없이(`saramin_in_site: false`) 만든 번들은 이 가드를 그대로 통과한다.

## 소형 테스트 번들로 파이프라인 검증 (실제 사이트를 덮어쓰지 않음)
1. `python -I -X utf8 pipeline/make_test_bundle.py` → `dist-test/` 에 가상 기업(`TEST …`, 번호 99999xxx, 실제 기업·급여 없음)의 수 KB 번들 + `manifest.json`(`test_bundle: true`) + `policy_manifest.json`.
2. 저장소에 Release(예: 태그 `pipeline-test-1`, **초안/사전 릴리스 권장**)를 만들고 세 파일을 올린 뒤 Actions → pay-watch-pages → Run workflow, `release_tag=pipeline-test-1`.
3. `bundle` job 이 번들 내려받기 → 무결성 → 사람인 직접 검사 → 공개 검사 → 링크 점검을 모두 실행하고, 테스트 번들이면 **Pages 아티팩트를 만들지 않고** `test-site` 점검용 아티팩트(보관 1일)만 남긴다. `deploy` job 은 `test_bundle == 'false'` 일 때만 실행되므로 테스트 번들은 Pages 에 도달할 수 없다.
- 같은 흐름을 로컬에서도 재현한다(`tests/test_phase14_3.py::test_synthetic_test_bundle_passes_the_whole_pipeline_without_touching_the_real_site`).

## 420MB 번들 배포 시 예상 제약 (GitHub Pages 한도 기준)
측정값(이 컴퓨터): `site/` 420.9MB(420,862,081바이트), 1,705파일, 최대 파일 1.6MB, `data/d` 347MB(82%), 로컬 `check_public` 21초(원자료 대조 제외)·`check_links` 1초. 미측정(추정): zip 크기·Actions 단계 시간.
| 항목 | 한도/제약 | 현재 | 판단 |
|---|---|---|---|
| 게시 사이트 크기 | 1GB 이하 | 421MB(약 41%) | 여유 약 580MB. `data/d` 가 82% 라 데이터가 2배 가까이 늘면 위험 |
| 배포 제한 시간 | 약 10분 | 미측정 | 매 배포마다 420MB 전체를 다시 올림(증분 없음). 번들 내려받기·압축 해제·검사는 약 2분 내(검사 22초 측정), 아티팩트 업로드(tar+gzip)와 Pages 배포가 대부분. 수 분 걸릴 가능성이 있어 첫 실제 배포에서 시간을 기록하고 8분을 넘으면 데이터 축소를 검토 |
| Release 자산 | 파일당 2GiB | zip 추정 80~100MB(JSON 샘플 gzip 비율 0.19로 추정, 실제 생성 안 함) | 여유 |
| 트래픽 | 소프트 월 100GB | 첫 화면 29KB + 검색 시작 시 91KB+342KB(gzip) | 방문당 약 0.5MB 이하라 월 20만 방문 수준까지 여유(추정) |
| 파일 수 | 명시적 한도 없음 | 1,705 | 문제 없음 |
- 완화 방안(필요할 때만, 기능 훼손 없는 범위): `data/d` 사업장 상세 샤드의 불필요 필드·정밀도 축소, 자주 안 쓰는 연도 시계열 분리, 필요 시 상세 데이터를 별도 정적 호스팅으로 분리.
- 한도 수치(1GB·10분·100GB)는 GitHub 문서 기준 값으로, 실제 배포 직전 최신 문서에서 다시 확인한다.
