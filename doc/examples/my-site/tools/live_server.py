"""Serve a directory, and reload each open page when the directory's content changes: live_server.py DIRECTORY [PORT]

Port 0 picks a free port. The reloading script joins a page only as it is served, so the built files stay as they would be published.
"""

import contextlib
import hashlib
import http.server
import os
import sys

VERSION_PATH = "/__version"
RELOAD_SCRIPT = """<script>
let seen = "%s";
setInterval(async () => {
  try {
    const version = await (await fetch("%s")).text();
    if (version !== seen) location.reload();
  } catch {
    // The server is restarting, so ask again on the next tick.
  }
}, 300);
</script>
"""

directory = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000


def calc_version():
    digest = hashlib.sha256()
    for folder, _, names in sorted(os.walk(directory)):
        for name in sorted(names):
            path = os.path.join(folder, name)
            digest.update(path.encode())
            try:
                with open(path, "rb") as file:
                    digest.update(file.read())
            except FileNotFoundError:
                # `fac clean` can delete a file between the listing and this read.
                continue
    return digest.hexdigest()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == VERSION_PATH:
            self.send_body(calc_version().encode(), "text/plain")
            return
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if not path.endswith(".html") or not os.path.exists(path):
            super().do_GET()
            return
        # Read the version first, so a page written in between reloads instead of going stale.
        script = RELOAD_SCRIPT % (calc_version(), VERSION_PATH)
        with open(path, "rb") as file:
            self.send_body(file.read() + script.encode(), "text/html; charset=utf-8")

    def send_body(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if self.path != VERSION_PATH:
            super().log_message(format, *args)


with http.server.ThreadingHTTPServer(("localhost", port), Handler) as server:
    print(f"Serving http://localhost:{server.server_address[1]}", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
