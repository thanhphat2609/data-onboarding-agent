"""Fetch page content: plain HTTP first, headless browser as fallback.

Ported from web-search-mcp (src/enhanced-content-extractor.ts). Same strategy: HTTP with browser-like
headers; when that fails in a way a browser can fix (403/429/503, timeout, "enable JavaScript"/captcha
pages, near-empty content, JavaScript-heavy sites) the page is loaded in headless Chromium. PDFs are skipped.
Difference: content containing the word "robot" is no longer treated as a bot-detection page (it matched
robots.txt docs).

Environment: MAX_CONTENT_LENGTH (characters per page, default 500000), DEFAULT_TIMEOUT (ms, default 6000).
"""
import logging
import os
from urllib.parse import urlparse

import requests

from agent.research.websearch import browser
from agent.research.websearch.extract import html_to_text
from agent.research.websearch.models import Page

log = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", "500000"))
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "6000")) / 1000
MAX_PAGE_BYTES = 5_000_000
HEADERS = {
    "User-Agent": browser.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
JS_HEAVY_HOSTS = ("twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com", "reddit.com", "medium.com")
BLOCK_MARKERS = ("Please enable JavaScript", "Access Denied", "403 Forbidden", "captcha", "unusual traffic")


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str = "", browser_may_help: bool = False):
        super().__init__(message)
        self.status, self.body, self.browser_may_help = status, body, browser_may_help


def is_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _low_quality(text: str) -> bool:
    return len(text.strip()) < 100 or any(m in text for m in BLOCK_MARKERS)


def _http(url: str, timeout: float, max_chars: int) -> Page:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
    except requests.Timeout as exc:
        raise FetchError("Request timeout", browser_may_help=True) from exc
    except requests.RequestException as exc:
        raise FetchError(f"Network error: {exc}") from exc
    body = resp.raw.read(MAX_PAGE_BYTES, decode_content=True).decode(resp.encoding or "utf-8", errors="replace")
    if resp.status_code >= 400:
        message = {403: "403 Forbidden - Access denied", 404: "404 Not found"}.get(resp.status_code, f"HTTP {resp.status_code}")
        raise FetchError(message, resp.status_code, body, browser_may_help=resp.status_code in (403, 429, 503))
    ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype:
        raise FetchError("PDF files are not supported")
    if "html" not in ctype and "text" not in ctype:
        raise FetchError(f"Not a web page ({ctype or 'unknown type'})")
    title, text = html_to_text(body, max_chars) if "html" in ctype else ("", body[:max_chars])
    if _low_quality(text):
        raise FetchError("Low quality content detected - likely bot detection or a JavaScript-only page", body=body, browser_may_help=True)
    return Page(url=url, title=title or url, content=text, via="http")


def _browser_may_help(exc: FetchError, url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return (
        exc.browser_may_help
        or any(m.lower() in exc.body.lower() for m in ("please enable javascript", "captcha", "unusual traffic"))
        or any(host == h or host.endswith("." + h) for h in JS_HEAVY_HOSTS)
    )


def fetch(url: str, timeout: float = DEFAULT_TIMEOUT, max_chars: int = MAX_CONTENT_LENGTH) -> Page:
    """Main text of one page; never raises (fetch_status="error" with the reason instead)."""
    if not url.startswith(("http://", "https://")):
        return Page(url=url, fetch_status="error", error="Only http(s) URLs are supported")
    try:
        return _http(url, timeout, max_chars)
    except FetchError as exc:
        if not (_browser_may_help(exc, url) and browser.available()):
            return Page(url=url, fetch_status="error", error=str(exc))
        log.info("HTTP failed for %s (%s), trying the headless browser", url, exc)
        try:
            html, title = browser.get_html(url, timeout=min(timeout + 2, 8), wait_for="article, main, .content, .post-content, .entry-content")
            title_from_html, text = html_to_text(html, max_chars)
            if _low_quality(text):
                return Page(url=url, fetch_status="error", error=f"{exc}; the browser got no readable content either", via="browser")
            return Page(url=url, title=title or title_from_html or url, content=text, via="browser")
        except Exception as browser_exc:  # noqa: BLE001
            return Page(url=url, fetch_status="error", error=f"{exc}; browser: {browser_exc}", via="browser")

