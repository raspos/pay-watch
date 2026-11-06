"""GitHub Release 자산 공개 범위 점검(PHASE 14.3 보강). 공개 저장소의 Release 자산은 누구나 내려받을 수 있으므로, 사람인 게시·재배포 권한이 확인되기 전에는
사람인 데이터가 든 번들을 공개 저장소 Release 에 둘 수 없다. manifest 의 표시를 믿지 않고 zip 안의 파일 이름을 직접 본다.
규칙: 번들에 사람인 파일(data/pay/, data/finder/sm_entities.json)이 있으면
  - 권한 확인(permitted)이면 통과
  - 비공개 저장소이면 Release 자산 보관만 허용(Pages 배포는 별도로 pages.yml 이 권한 없이는 차단)
  - 공개 저장소이고 권한 미확인이면 차단(종료 코드 2)
사람인 파일이 없으면 통과. release-guard.yml 이 Release 게시·수정 시 자동 실행하고, 차단되면 Release 를 초안으로 되돌리고 번들 자산을 지운다.
실행: python -I -X utf8 pipeline/release_guard.py <번들폴더> --repo-private true|false --permitted true|false"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

SARAMIN_MARKERS = ("data/pay/", "data/finder/sm_entities.json")


def bundle_has_saramin(zip_path: Path) -> bool:
    with zipfile.ZipFile(zip_path) as z:
        return any(n.startswith(SARAMIN_MARKERS[0]) or n == SARAMIN_MARKERS[1] for n in z.namelist())


def decide(has_saramin: bool, repo_private: bool, permitted: bool) -> tuple[bool, str]:
    if not has_saramin:
        return True, "사람인 데이터 없음: 통과"
    if permitted:
        return True, "사람인 데이터 포함, 게시·재배포 권한 확인됨: 통과"
    if repo_private:
        return True, "사람인 데이터 포함, 권한 미확인: 비공개 저장소 Release 보관만 허용(Pages 배포는 별도로 차단)"
    return False, "차단: 공개 저장소 Release 에 사람인 데이터가 든 번들을 둘 수 없음(권한 미확인). Release 를 초안으로 되돌리고 자산을 지워야 함"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle_dir")
    ap.add_argument("--repo-private", required=True, choices=["true", "false"])
    ap.add_argument("--permitted", required=True, choices=["true", "false"])
    a = ap.parse_args(argv)
    b = Path(a.bundle_dir)
    m = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    has = bundle_has_saramin(b / m["zip"])
    if has != bool(m.get("saramin_included")):
        print("경고: manifest 의 saramin_included 가 실제 zip 내용과 다름(zip 내용을 기준으로 판정)")
    ok, msg = decide(has, a.repo_private == "true", a.permitted == "true")
    print(msg)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
