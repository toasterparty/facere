"""A stand-in for a CMS's HTTP REST API, holding pages in memory, so the example runs without a real one.

`python tools/fake_cms.py` serves it at the URL the example's `fac.py` names, until interrupted.
"""

import contextlib
import http.server
import json

PORT = 8000


class FakeCms(http.server.HTTPServer):
    """Serves `/pages` on 127.0.0.1, one request at a time.

    GET returns every page as a JSON object keyed by slug, HEAD only its headers, and PUT `/pages/SLUG` stores one page. Each response carries an ETag that changes with every stored page. `pages` holds what was stored, and `requests` lists each request as `METHOD PATH`.
    """

    def __init__(self, port: int = PORT) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.pages: dict[str, str] = {}
        self.version = 0
        self.requests: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_port}/pages"


class _Handler(http.server.BaseHTTPRequestHandler):
    @property
    def cms(self) -> FakeCms:
        assert isinstance(self.server, FakeCms)
        return self.server

    def do_HEAD(self) -> None:
        self._send_pages(has_body=False)

    def do_GET(self) -> None:
        self._send_pages(has_body=True)

    def do_PUT(self) -> None:
        self.cms.requests.append(f"PUT {self.path}")
        slug = self.path.removeprefix("/pages/")
        if slug == self.path or not slug or "/" in slug:
            self.send_error(404)
            return
        length = int(self.headers["Content-Length"])
        self.cms.pages[slug] = self.rfile.read(length).decode("utf-8")
        self.cms.version += 1
        self.send_response(204)
        self.send_header("ETag", self._calc_etag())
        self.end_headers()

    def _send_pages(self, has_body: bool) -> None:
        self.cms.requests.append(f"{self.command} {self.path}")
        if self.path != "/pages":
            self.send_error(404)
            return
        payload = json.dumps(self.cms.pages).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("ETag", self._calc_etag())
        self.end_headers()
        if has_body:
            self.wfile.write(payload)

    def _calc_etag(self) -> str:
        return f'"{self.cms.version}"'


if __name__ == "__main__":
    with FakeCms() as cms, contextlib.suppress(KeyboardInterrupt):
        print(f"serving {cms.url}", flush=True)
        cms.serve_forever()
