"""공개용 빌드 한 번에: build_site(코드) → 공개 데이터 정책 → 통합 검색 색인 → 공개 검사. 연구용 자료는 어디에도 쓰지 않는다.
data/ 자체(법인·사업장 샤드)는 별도 파이프라인(build_corp.py 등)이 만들며, 그 뒤에 이 스크립트를 실행한다.
실행: python -I -X utf8 pipeline/build_public.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-I", "-X", "utf8"]
for step in ("build_site.py", "apply_public_policy.py", "build_saramin.py", "export_est_public.py", "build_finder.py", "check_public.py"):
    print("==", step)
    r = subprocess.run(PY + [str(ROOT / "pipeline" / step)], cwd=ROOT)
    if r.returncode == 2 and step == "check_public.py":      # 사람인 게시 권한 미확인: 빌드는 끝났지만 배포는 차단된다(정상 동작)
        sys.exit(2)
    if r.returncode:
        sys.exit(r.returncode)
