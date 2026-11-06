"""프런트엔드 순수 로직(node --test) 을 pytest 실행에 포함한다. node 가 없으면 건너뛴다."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 가 설치되어 있지 않음")
def test_js_unit_tests_pass():
    files = sorted(str(p) for p in (ROOT / "tests/js").glob("*.test.mjs"))
    r = subprocess.run(["node", "--test", *files], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
