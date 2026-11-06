"""연구용 미리보기(preview/)를 **localhost(127.0.0.1) 에서만** 서빙한다. python -m http.server 는 기본으로 모든 네트워크 인터페이스(0.0.0.0)에 열리므로 쓰지 않는다.
실행: python -I -X utf8 pipeline/serve_preview.py [포트=8791]   (먼저 pipeline/build_site.py → pipeline/build_preview.py)"""
import functools
import http.server
import sys
from pathlib import Path

HOST = "127.0.0.1"
ROOT = Path(__file__).resolve().parents[1]


def make_server(port: int = 8791, directory: Path | None = None) -> http.server.ThreadingHTTPServer:
    directory = Path(directory or ROOT / "preview")
    if not directory.exists():
        raise SystemExit("preview/ 가 없습니다. 먼저 pipeline/build_preview.py 를 실행하세요")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    return http.server.ThreadingHTTPServer((HOST, port), handler)          # 항상 loopback 에만 바인딩


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    srv = make_server(port)
    print(f"preview: http://{HOST}:{port}/exp.html  (이 PC에서만 접근 가능, 종료: Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
