import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_quotes_the_recorded_mock_run():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    board = json.loads((ROOT / "site" / "data" / "scoreboard.json").read_text(encoding="utf-8"))
    assert board["provider"] == "mock"
    assert "mock" in readme.lower()
    assert "ollama" in readme.lower()
    assert board["recorded_at"] in readme
    assert "```mermaid" in readme
    for arm in ("with_router", "without_router"):
        for key in (
            "first_try_valid_display",
            "valid_after_retry_display",
            "mean_retries_display",
            "unrecoverable_display",
        ):
            token = board[arm][key].split()[0]
            assert token in readme, token
    for image in (
        "docs/images/scoreboard.png",
        "docs/images/trace-retry.png",
        "docs/images/trace-failsafe.png",
        "docs/images/scoreboard-phone.png",
    ):
        assert image in readme
        path = ROOT / image
        assert path.is_file()
        assert path.stat().st_size > 20_000
    assert "not deployed" in readme.lower() or "not deployed yet" in readme.lower()
    wrangler = (ROOT / "wrangler.toml").read_text(encoding="utf-8")
    assert 'pages_build_output_dir = "site"' in wrangler
