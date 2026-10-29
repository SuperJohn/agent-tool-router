import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from toolrouter.provider import OllamaProvider, ProviderError, provider_from_env


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.last = body  # type: ignore[attr-defined]
        content = '{"tool":"list_events","arguments":{"day":"2026-11-03"}}'
        payload = json.dumps({"message": {"content": content}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def test_ollama_sends_format_only_with_a_schema():
    httpd = _server()
    try:
        host, port = httpd.server_address[:2]
        provider = OllamaProvider("llama3.2:1b", f"http://{host}:{port}", seed=42, timeout=5)
        schema = {"type": "object", "properties": {"tool": {"type": "string"}}}
        text = provider.complete(
            messages=[{"role": "user", "content": "list the day"}],
            schema=schema,
            task_id="cal-02",
        )
        assert "list_events" in text
        sent = httpd.last
        assert sent["format"] == schema
        assert sent["options"] == {"temperature": 0, "seed": 42}
        assert sent["model"] == "llama3.2:1b"
        assert sent["stream"] is False

        provider.complete(messages=[{"role": "user", "content": "again"}], schema=None, task_id="cal-02")
        assert "format" not in httpd.last
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ollama_connection_refused_is_a_provider_error():
    provider = OllamaProvider("llama3.2:1b", "http://127.0.0.1:9", seed=42, timeout=2)
    with pytest.raises(ProviderError, match="Ollama request failed"):
        provider.complete(messages=[], schema=None, task_id="cal-01")


def test_provider_from_env(monkeypatch):
    monkeypatch.setenv("HL_PROVIDER", "mock")
    provider = provider_from_env({"cal-01": {"raw": ["{}"], "constrained": "{}", "retry": ["{}"]}})
    assert provider.name == "mock"
    monkeypatch.setenv("HL_PROVIDER", "ollama")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    with pytest.raises(SystemExit):
        provider_from_env({})
