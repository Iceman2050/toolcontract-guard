"""Local mock orders API whose behaviour DELIBERATELY disagrees with
fixtures/staging-api.json, so `toolcontract test` has real discrepancies
to detect:

1. It performs no validation at all: limit=0, limit=101 and
   status=<not-in-enum> are all accepted with HTTP 200, although the
   documented contract forbids them (accepts-forbidden).
2. Its 200 body violates the documented response schema: `total` is the
   string "zero", not the documented integer (HTTP-200-but-wrong — the
   silent-failure case).

Localhost only. Run:  python3 fixtures/mock_server.py [port]
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/orders"):
            body = json.dumps({"items": [], "total": "zero"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/health"):
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b'{"error": "not found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *args):
        pass


def make_server(port=0):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = make_server(port)
    print(f"mock orders API on http://127.0.0.1:{srv.server_address[1]}")
    srv.serve_forever()
