"""Web search without API keys: SearXNG, then Bing, then Brave, then DuckDuckGo; the first good-enough result list wins.

SearXNG (not in web-search-mcp) is a self-hosted metasearch engine, a container in the compose file
(infrastructure/searxng/). It asks several engines at once, so one engine rate-limiting this network no longer
means no results. Used when SEARXNG_URL is set; the scrapers below stay as the fallback.

Ported from web-search-mcp (src/search-engine.ts). Same engine order, result parsing (selectors) and
quality check: results score by query keywords and word pairs found in title/description/URL; a score
>= 0.8 returns at once, >= RELEVANCE_THRESHOLD returns from Brave/DuckDuckGo, otherwise the best list
across all engines is used. Differences:
- Bing and Brave are only used when the headless browser is available (browser.py): over plain HTTP they
  answer automated clients with generic results or 429. Bing is opened with its search URL directly (the
  original first typed the query into the homepage form).
- The quality score drops the original's off-topic word penalty ("team", "price", "car"…), which
  penalised ordinary data-platform queries.
- Bing click-tracking links (bing.com/ck/a?…&u=a1<base64>) are decoded to the real URL, results are
  de-duplicated, and only http(s) URLs are kept.
- A last fallback engine, the `ddgs` package (see search_ddgs). Observed 2026-10-23: over plain HTTP, Bing
  answers bots with generic results (rejected by the quality check), Brave with 429 and html.duckduckgo.com
  with a bot challenge, so without a browser this fallback is what finds results.

Environment (same names as the original): ENABLE_RELEVANCE_CHECKING (default true), RELEVANCE_THRESHOLD
(default 0.3), FORCE_MULTI_ENGINE_SEARCH (default false). Added: SEARXNG_URL (default empty = no SearXNG).
"""
import base64
import logging
import os
import re
from urllib.parse import parse_qs, quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from agent.research.websearch import browser
from agent.research.websearch.models import SearchResponse, SearchResult
from agent.research.websearch.ratelimit import RateLimiter

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": browser.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_limiter = RateLimiter(max_per_minute=10)
_COMMON_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was",
    "were", "be", "been", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "must", "can", "group", "members",
}
_METADATA_SNIPPET_RE = re.compile(r"^\d+\s*(min|sec|hour|day|week|month|year)", re.I)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() not in ("0", "false", "no", "off")


# ---------- URL cleanup ----------

def _clean_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    # DuckDuckGo redirect: //duckduckgo.com/l/?uddg=<url>
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        if target := parse_qs(parsed.query).get("uddg", [""])[0]:
            return target
    # Bing click tracking: https://www.bing.com/ck/a?...&u=a1<base64url of the real URL>
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        u = parse_qs(parsed.query).get("u", [""])[0]
        if u.startswith("a1"):
            raw = u[2:] + "=" * (-len(u[2:]) % 4)
            try:
                return base64.urlsafe_b64decode(raw).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                pass
    return url


def _keep(results: list[SearchResult], title: str, url: str, snippet: str, max_results: int) -> None:
    url = _clean_url(url)
    if not (title and url.startswith(("http://", "https://"))) or len(results) >= max_results:
        return
    if any(r.url == url for r in results):
        return
    results.append(SearchResult(title=title, url=url, description=snippet or "No description available"))


# ---------- parsers (selectors from the original) ----------

def parse_bing(html: str, max_results: int) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    for selector in (".b_algo", ".b_result", ".b_card"):
        if results and len(results) >= max_results:
            break
        for el in soup.select(selector):
            link = next((a for s in ("h2 a", ".b_title a", "a[data-seid]") if (a := el.select_one(s))), None)
            if link is None:
                continue
            snippet = ""
            for s in (".b_caption p", ".b_snippet", ".b_descript", ".b_caption", ".b_caption > span", ".b_excerpt",
                      "p", ".b_algo_content p", ".b_algo_content", ".b_context"):
                if (node := el.select_one(s)) is not None:
                    candidate = node.get_text(" ", strip=True)
                    if len(candidate) > 20 and not _METADATA_SNIPPET_RE.match(candidate):
                        snippet = candidate
                        break
            _keep(results, link.get_text(" ", strip=True), link.get("href", ""), snippet, max_results)
    return results


def parse_brave(html: str, max_results: int) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    for selector in ("[data-type='web']", ".result", ".fdb"):
        if results and len(results) >= max_results:
            break
        for el in soup.select(selector):
            title, url = "", ""
            # Brave's current markup (2026): <a href> wraps a site-name breadcrumb and .search-snippet-title.
            if (node := el.select_one(".search-snippet-title")) is not None and (a := node.find_parent("a")) is not None:
                title, url = node.get_text(" ", strip=True), a.get("href", "")
            else:  # the original's selectors
                for s in (".title a", "h2 a", ".result-title a", "a[href*='://']", ".snippet-title a"):
                    if (a := el.select_one(s)) is not None:
                        title, url = a.get_text(" ", strip=True), a.get("href", "")
                        if title and url.startswith("http"):
                            break
            if not title:
                lines = [ln for ln in el.get_text("\n", strip=True).split("\n") if ln.strip()]
                title = lines[0] if lines else ""
            snippet = next(
                (node.get_text(" ", strip=True)
                 for s in (".generic-snippet .content", ".snippet-content", ".snippet-description", ".snippet", ".description", "p")
                 if (node := el.select_one(s)) is not None),
                "",
            )
            _keep(results, title, url, snippet, max_results)
    return results


def parse_duckduckgo(html: str, max_results: int) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    for el in soup.select(".result"):
        link = el.select_one(".result__title a")
        if link is None:
            continue
        snippet = el.select_one(".result__snippet")
        _keep(results, link.get_text(" ", strip=True), link.get("href", ""), snippet.get_text(" ", strip=True) if snippet else "", max_results)
    return results


# ---------- engines ----------

def _load(url: str, timeout: float, wait_for: str) -> str:
    """Search page HTML in the headless browser, 2 attempts like the original."""
    last: Exception | None = None
    for _ in range(2):
        try:
            return browser.get_html(url, timeout=max(timeout, 6.0), wait_for=wait_for)[0]
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"browser could not load {url}: {last}")


def search_bing(query: str, num_results: int, timeout: float) -> list[SearchResult]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={min(num_results, 10)}&form=QBLH"
    return parse_bing(_load(url, timeout, ".b_algo, .b_result"), num_results)


def search_brave(query: str, num_results: int, timeout: float) -> list[SearchResult]:
    url = f"https://search.brave.com/search?q={quote_plus(query)}&source=web"
    return parse_brave(_load(url, timeout, "[data-type='web']"), num_results)


def search_duckduckgo(query: str, num_results: int, timeout: float) -> list[SearchResult]:
    resp = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return parse_duckduckgo(resp.text, num_results)


def search_searxng(query: str, num_results: int, timeout: float) -> list[SearchResult]:
    """Not in the original: the self-hosted SearXNG's JSON API (results merged from several engines)."""
    resp = requests.get(f"{os.getenv('SEARXNG_URL', '').rstrip('/')}/search",
                        params={"q": query, "format": "json", "language": "en"}, timeout=max(timeout, 8.0))
    resp.raise_for_status()
    results: list[SearchResult] = []
    for hit in resp.json().get("results", []):
        _keep(results, hit.get("title", ""), hit.get("url", ""), hit.get("content", ""), num_results)
    return results


def search_ddgs(query: str, num_results: int, timeout: float) -> list[SearchResult]:
    """Not in the original: the `ddgs` package, which reaches DuckDuckGo through endpoints that still answer
    when html.duckduckgo.com serves its bot challenge (HTTP 202) to plain HTTP clients."""
    from ddgs import DDGS

    results: list[SearchResult] = []
    for hit in DDGS(timeout=max(int(timeout), 10)).text(query, max_results=num_results):
        _keep(results, hit.get("title", ""), hit.get("href", ""), hit.get("body", ""), num_results)
    return results


# (name, function, needs the headless browser)
ENGINES = [
    ("SearXNG", search_searxng, False),
    ("Bing", search_bing, True),
    ("Brave", search_brave, True),
    ("DuckDuckGo", search_duckduckgo, False),
    ("DuckDuckGo (ddgs)", search_ddgs, False),
]


def assess_quality(results: list[SearchResult], query: str) -> float:
    """Average share of query keywords (plus a bonus per matching word pair) found in each result."""
    if not results:
        return 0.0
    words = [w for w in re.sub(r"[^\w\s]", " ", query.lower()).split() if len(w) > 2 and w not in _COMMON_WORDS]
    if not words:
        return 0.5
    phrases = [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    if len(words) >= 3:
        phrases.append(" ".join(words[:3]))
    total = 0.0
    for r in results:
        text = f"{r.title} {r.description} {r.url}".lower()
        keyword_ratio = sum(w in text for w in words) / len(words)
        total += min(1.0, keyword_ratio + 0.3 * sum(p in text for p in phrases))
    return total / len(results)


def search(query: str, num_results: int = 5, timeout: float = 12.0) -> SearchResponse:
    """Search the web; returns the results of the first engine with good enough results (see module doc)."""
    query = query.strip()[:1000]
    check = _env_flag("ENABLE_RELEVANCE_CHECKING", True)
    threshold = float(os.getenv("RELEVANCE_THRESHOLD", "0.3"))
    force_all = _env_flag("FORCE_MULTI_ENGINE_SEARCH", False)

    def run() -> SearchResponse:
        best, best_engine, best_quality = [], "None", 0.0
        per_engine = min(timeout / 3, 4.0)
        engines = [(n, f) for n, f, needs_browser in ENGINES
                   if (browser.available() or not needs_browser) and (n != "SearXNG" or os.getenv("SEARXNG_URL"))]
        for i, (name, engine) in enumerate(engines):
            try:
                results = engine(query, num_results, per_engine)
            except Exception as exc:  # noqa: BLE001 — scraping can fail in many ways; try the next engine
                log.info("%s search failed: %s", name, exc)
                continue
            if not results:
                continue
            quality = assess_quality(results, query) if check else 1.0
            log.info("%s: %d results, quality %.2f", name, len(results), quality)
            if quality > best_quality:
                best, best_engine, best_quality = results, name, quality
            if not force_all and (quality >= 0.8 or (quality >= threshold and name != "Bing")):
                return SearchResponse(query, name, results)
            if i == len(engines) - 1 and best:
                return SearchResponse(query, best_engine, best)
        return SearchResponse(query, best_engine, best)

    return _limiter.execute(run)
