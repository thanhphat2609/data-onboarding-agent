"""Optional headless Chromium (Playwright) for search engines and pages that need JavaScript.

Ported from web-search-mcp (src/browser-pool.ts and the browser parts of the search engine and content
extractor). Differences:
- Optional: until Chromium is downloaded (python -m playwright install chromium) everything runs over plain HTTP.
  WEBSEARCH_BROWSER=off turns it off even when installed.
- One short-lived browser per call instead of a pool: Playwright's sync API is bound to the thread that
  started it, and the web UI serves requests from several threads.
- Chromium only, a normal browser profile: no fingerprint spoofing or simulated mouse movement.
"""
import logging
import os
import threading

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
_BLOCKED_RESOURCES = {"image", "font", "media"}

_available: bool | None = None
_lock = threading.Lock()


def available() -> bool:
    """True when Playwright and its Chromium are installed and not turned off (checked once)."""
    global _available
    if os.getenv("WEBSEARCH_BROWSER", "auto").strip().lower() in ("0", "off", "false", "no"):
        return False
    with _lock:
        if _available is None:
            try:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:  # a real launch: the installed build may be the headless shell only
                    p.chromium.launch(headless=True, args=["--no-sandbox"]).close()
                    _available = True
            except Exception as exc:  # noqa: BLE001 — not installed, no driver, no browser download
                log.info("Headless browser not available, using HTTP only: %s", exc)
                _available = False
        return _available


def get_html(url: str, timeout: float = 8.0, wait_for: str | None = None) -> tuple[str, str]:
    """Load `url` in headless Chromium and return (html, page title). Images, fonts and media are not loaded."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    def load(extra_args: list[str]) -> tuple[str, str]:
        """Opens the page in headless Chromium, blocking heavy resources; returns its HTML and title."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", *extra_args])
            try:
                context = browser.new_context(user_agent=USER_AGENT, locale="en-US", viewport={"width": 1366, "height": 768})
                page = context.new_page()
                page.route(
                    "**/*",
                    lambda route: route.abort() if route.request.resource_type in _BLOCKED_RESOURCES else route.continue_(),
                )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=3000)
                    except PlaywrightError:
                        pass  # proceed with whatever rendered
                return page.content(), page.title()
            finally:
                browser.close()

    try:
        return load([])
    except PlaywrightError as exc:
        # Some sites break over HTTP/2 in headless Chromium; the original retried with HTTP/1.1.
        if "HTTP2" in str(exc) or "ERR_HTTP2" in str(exc):
            return load(["--disable-http2"])
        raise
