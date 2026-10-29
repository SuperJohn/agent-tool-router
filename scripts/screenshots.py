"""Capture the replay site with headless Chromium.

Requires Playwright and a local Chrome. Not used by CI.

    python3 -m pip install playwright
    python3 scripts/screenshots.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from toolrouter.dataset import repo_root
from toolrouter.serve import serve_background

ROOT = repo_root()
OUT = ROOT / "docs" / "images"
CHROME = "/usr/local/bin/google-chrome"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = serve_background()
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}/"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=CHROME,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
            page.goto(base + "?static=1", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function("() => document.fonts.status === 'loaded'", timeout=20000)
            page.wait_for_selector("[data-metric=first_try_valid]", timeout=20000)
            assert "72.7%" in page.locator("#scoreboard").inner_text()
            assert "27.3%" in page.locator("#scoreboard").inner_text()
            assert "mock" in page.locator("#run-meta").inner_text()
            page.locator("#hero").screenshot(path=str(OUT / "scoreboard.png"))

            page.goto(base + "?static=1#cal-04/with", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#stage h2")
            stage = page.locator("#stage").inner_text().lower()
            assert "end must be after start" in stage
            assert "retry prompt" in stage
            assert "2026-11-05t13:00:00" in stage
            assert "corrected call" in stage
            page.locator("#stage").screenshot(path=str(OUT / "trace-retry.png"))

            page.locator("button", has_text="Without router").click()
            page.wait_for_selector(".failsafe")
            baseline = page.locator("#stage").inner_text().lower()
            assert "unrecoverable" in baseline
            assert "end must be after start" in baseline
            assert page.locator("button", has_text="Re-run this arm locally").count() == 0

            page.goto(base + "#cal-04/with", wait_until="domcontentloaded", timeout=60000)
            page.locator("button", has_text="Re-run this arm locally").click()
            page.wait_for_selector("text=Live re-run matches the recorded trace.")

            page.goto(base + "?static=1#cal-08/with", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector(".failsafe")
            stuck = page.locator("#stage").inner_text().lower()
            assert "tool not executed" in stuck
            assert "executed" in stuck
            page.locator("#stage").screenshot(path=str(OUT / "trace-failsafe.png"))

            page.goto(base + "?static=1#look-04/with", wait_until="domcontentloaded", timeout=60000)
            wrong = page.locator("#stage").inner_text().lower()
            assert "do not match" in wrong

            mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            mobile.goto(base + "?static=1", wait_until="domcontentloaded", timeout=60000)
            mobile.wait_for_selector("[data-metric=first_try_valid]")
            overflow = mobile.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 1:
                raise SystemExit(f"mobile page overflows by {overflow}px")
            mobile.locator("#hero").screenshot(path=str(OUT / "scoreboard-phone.png"))
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
    for name in ("scoreboard.png", "trace-retry.png", "trace-failsafe.png", "scoreboard-phone.png"):
        path = OUT / name
        print(f"{path} {path.stat().st_size}")


if __name__ == "__main__":
    main()
