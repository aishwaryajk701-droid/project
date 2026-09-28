"""Minimal static-file server used by the Docker image to serve the built frontend
and proxy /api to the backend container."""

import http.server
import os
import urllib.request

BACKEND = os.environ.get("BACKEND_URL", "http://backend:8001")
STATIC = "/app/frontend/dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=STATIC, **kw)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def _proxy(self):
        try:
            with urllib.request.urlopen(BACKEND + self.path) as r:
                body = r.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_error(502, str(exc))


if __name__ == "__main__":
    http.server.HTTPServer(("0.0.0.0", 3000), Handler).serve_forever()
