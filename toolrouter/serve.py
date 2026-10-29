"""Local replay server.

Serves ``site/`` and a small API that re-runs one task through the same
router the recording used. Cloudflare Pages serves the static files only.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from toolrouter.bench import run_task
from toolrouter.dataset import load_dataset, repo_root
from toolrouter.provider import provider_from_env


def _send_json(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def make_httpd(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    dataset = load_dataset()
    provider = provider_from_env(dataset.recordings)
    max_retries = int(os.environ.get("HL_MAX_RETRIES", "2"))
    site = repo_root() / "site"

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, directory=str(site), **kwargs)

        def log_message(self, fmt: str, *args: Any) -> None:
            # Request logs add noise in tests. The ready line is enough.
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/health":
                _send_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "provider": provider.name,
                        "dataset": dataset.display,
                        "tasks": len(dataset.tasks),
                        "max_retries": max_retries,
                    },
                )
                return
            if path.startswith("/api/"):
                _send_json(self, 404, {"ok": False, "error": "not found"})
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/api/run":
                _send_json(self, 404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length > 1_000_000:
                _send_json(self, 400, {"ok": False, "error": "body too large"})
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except json.JSONDecodeError:
                _send_json(self, 400, {"ok": False, "error": "invalid JSON"})
                return
            task_id = body.get("task_id")
            arm = body.get("arm", "with_router")
            if not isinstance(task_id, str) or arm not in {"with_router", "without_router"}:
                _send_json(self, 400, {"ok": False, "error": "task_id and arm are required"})
                return
            try:
                payload = run_task(
                    dataset,
                    provider,
                    task_id,
                    arm=arm,
                    max_retries=max_retries,
                )
            except KeyError:
                _send_json(self, 404, {"ok": False, "error": f"unknown task {task_id}"})
                return
            _send_json(self, 200, payload)

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


def serve(host: str = "127.0.0.1", port: int | None = None) -> None:
    if port is None:
        port = int(os.environ.get("HL_PORT", "8787"))
    httpd = make_httpd(host, port)
    bound_host, bound_port = httpd.server_address[:2]
    print(f"agent-tool-router at http://{bound_host}:{bound_port}")
    print("static replay of site/data, plus POST /api/run to execute one task")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def serve_background(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    httpd = make_httpd(host, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd
