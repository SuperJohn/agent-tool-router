import json
import urllib.request

from toolrouter.bench import run_task
from toolrouter.dataset import load_dataset
from toolrouter.provider import MockProvider
from toolrouter.serve import serve_background


def test_health_and_rerun_match_the_library():
    httpd = serve_background()
    try:
        host, port = httpd.server_address[:2]
        base = f"http://{host}:{port}"
        with urllib.request.urlopen(base + "/api/health") as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["ok"] is True
        assert health["provider"] == "mock"
        assert health["tasks"] == 22

        with urllib.request.urlopen(base + "/") as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "agent-tool-router" in html
        assert "googleapis" not in html
        assert "cdn." not in html

        request = urllib.request.Request(
            base + "/api/run",
            data=json.dumps({"task_id": "cal-04", "arm": "with_router"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
        dataset = load_dataset()
        expected = run_task(
            dataset,
            MockProvider(dataset.recordings),
            "cal-04",
            arm="with_router",
            max_retries=2,
        )
        assert payload == expected
        assert payload["outcome"]["validated"] is True
        assert payload["outcome"]["retries"] == 1
    finally:
        httpd.shutdown()
        httpd.server_close()
