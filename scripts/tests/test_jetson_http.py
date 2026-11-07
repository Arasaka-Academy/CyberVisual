from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jetson_deploy import DeployError, System, readiness


class LocalSystem(System):
    def active(self):
        return True


class HTTPReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {
            "/": b'<html><link rel="stylesheet" href="/assets/style.css"><script src="/assets/main.js"></script></html>',
            "/assets/style.css": b"body{color:white}",
            "/assets/main.js": b"a" * 100,
        }
        for name, data in self.files.items():
            target = self.root / "frontend/dist" / ("index.html" if name == "/" else name.lstrip("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.frame = 100
        self.slow = False
        self.slow_headers = False
        self.slow_chunk_header = False
        self.error_asset = False
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if fixture.slow_headers:
                    try:
                        self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                        for unused in range(20):
                            self.wfile.write(b"x")
                            self.wfile.flush()
                            time.sleep(0.05)
                        self.wfile.write(b"\r\nContent-Length: 0\r\n\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                if self.path == "/healthz":
                    content = b'{"ok":true}'
                elif self.path == "/api/status":
                    fixture.frame += 1
                    content = json.dumps({"camera": {"connected": True, "source": "camera"},
                                          "model": {"loaded": True, "backend": "opencv", "path": "private-model"},
                                          "last_frame_ts": fixture.frame}).encode()
                else:
                    content = fixture.files[self.path]
                self.send_response(503 if fixture.error_asset and self.path.endswith(".js") else 200)
                chunked = fixture.slow_chunk_header and self.path.endswith(".js")
                if chunked:
                    self.send_header("Transfer-Encoding", "chunked")
                else:
                    self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                try:
                    if chunked:
                        self.wfile.write(b"1;")
                        for unused in range(20):
                            self.wfile.write(b"x")
                            self.wfile.flush()
                            time.sleep(0.05)
                        self.wfile.write(b"\r\nx\r\n0\r\n\r\n")
                    elif fixture.slow and self.path.endswith(".js"):
                        for value in content:
                            self.wfile.write(bytes([value]))
                            self.wfile.flush()
                            time.sleep(0.05)
                    else:
                        self.wfile.write(content)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format, *arguments):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def test_real_http_checks_served_assets_and_frame_progress(self):
        system = LocalSystem()
        system.sleep = lambda seconds: None
        checks, warning = readiness(system, self.root, self.port, timeout=5)
        self.assertTrue(checks["assets"])
        self.assertGreaterEqual(checks["frame_advances"], 2)
        self.assertFalse(warning)

    def test_asset_error_is_not_hidden_by_a_healthy_api(self):
        self.error_asset = True
        with self.assertRaisesRegex(DeployError, "business_not_ready"):
            readiness(LocalSystem(), self.root, self.port, timeout=0.1)

    def test_slow_body_cannot_extend_the_business_deadline(self):
        self.slow = True
        started = time.monotonic()
        with self.assertRaisesRegex(DeployError, "business_not_ready"):
            readiness(LocalSystem(), self.root, self.port, timeout=0.15)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_slow_headers_cannot_extend_the_business_deadline(self):
        self.slow_headers = True
        started = time.monotonic()
        with self.assertRaisesRegex(DeployError, "business_not_ready"):
            readiness(LocalSystem(), self.root, self.port, timeout=0.15)
        self.assertLess(time.monotonic() - started, 0.6)

    def test_slow_chunk_headers_cannot_extend_the_business_deadline(self):
        self.slow_chunk_header = True
        started = time.monotonic()
        with self.assertRaisesRegex(DeployError, "business_not_ready"):
            readiness(LocalSystem(), self.root, self.port, timeout=0.15)
        self.assertLess(time.monotonic() - started, 0.6)


if __name__ == "__main__":
    unittest.main()
