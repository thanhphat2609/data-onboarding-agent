"""Web research without the network: on-topic checks, history sentences, known docs, cache, learned links, engines."""
import sqlite3

from agent import config
from agent.research import cache, investigate as inv, learned, websearch
from agent.research.websearch import engines
from agent.research.websearch.models import Page, SearchResponse, SearchResult
from agent.workflow.sessions import SessionStore

GSC = "google search console"


def result(title, url, description=""):
    return SearchResult(title=title, url=url, description=description)


def test_a_result_must_name_the_source_in_its_title_or_url():
    words = inv._source_words(GSC)
    assert inv._about_source(result("Usage Limits | Search Console API", "https://developers.google.com/webmaster-tools/limits"), words)
    # Named only in the description: another Google product.
    assert not inv._about_source(result("API dimensions and metrics | Google Analytics",
                                        "https://developers.google.com/analytics/x", "link Google Search Console"), words)
    assert not inv._about_source(result("Quota | Indexing API", "https://developers.google.com/search/apis/indexing-api"), words)


def test_short_words_between_the_source_words_are_allowed():
    assert inv._about_source(result("ERP export guide", "https://x/erp-on-postgresql"), inv._source_words("erp on postgresql"))


def test_history_sentences_need_retention_words_or_a_number():
    passages = inv.passages(
        "Current user behavior does not affect historical audience membership in reports. "
        "Search Console stores 16 months of data for the performance report."
    )
    history = [p["text"] for p in passages if p["topic"] == "history"]
    assert history == ["Search Console stores 16 months of data for the performance report."]


def test_known_docs_by_name_and_alias():
    assert inv.known_docs(GSC)[0].startswith("https://developers.google.com/webmaster-tools")
    assert inv.known_docs("gsc") == inv.known_docs(GSC)
    assert inv.known_docs("appsflyer") == []


def test_cache_round_trip_and_off_switch(monkeypatch):
    cache.put("search", "q", [1, 2])
    assert cache.get("search", "q") == [1, 2]
    monkeypatch.setattr(config, "RESEARCH_CACHE_DAYS", 0)
    assert cache.get("search", "q") is None


def _fake_web(monkeypatch, results):
    calls = {"search": 0, "fetch": 0}

    def search(query, n=8):
        calls["search"] += 1
        return SearchResponse(query, "fake", list(results))

    def fetch(url, timeout=15):
        calls["fetch"] += 1
        return Page(url=url, title=url, content="Search Console stores 16 months of data. API quota per site.",
                    fetch_status="success")

    monkeypatch.setattr(websearch, "web_search", search)
    monkeypatch.setattr(websearch, "web_fetch", fetch)
    monkeypatch.setattr(config, "WEB_RESEARCH", True)
    return calls


REQUEST = {"sources": [GSC], "date_range": {"start": "2024-01-01"}, "refresh_frequency": "daily",
           "grain": "date x page", "eta": "2026-12-01"}


def test_second_run_comes_from_the_cache(monkeypatch):
    calls = _fake_web(monkeypatch, [result("How To Use Search Console", "https://developers.google.com/search/console-start")])
    first = inv.investigate(GSC, REQUEST, [])
    assert calls["search"] > 0
    calls.update(search=0, fetch=0)
    second = inv.investigate(GSC, REQUEST, [])
    assert calls == {"search": 0, "fetch": 0}
    assert [link["url"] for link in second["links"]] == [link["url"] for link in first["links"]]
    assert all(s["cached"] for s in second["searches"])


def test_known_docs_are_listed_even_when_every_search_fails(monkeypatch):
    _fake_web(monkeypatch, [])
    findings = inv.investigate(GSC, REQUEST, [])
    assert [link["url"] for link in findings["links"]][:4] == inv.known_docs(GSC)
    assert findings["links"][0]["found_for"] == ["known docs"]


def test_links_of_an_approved_request_are_learned(monkeypatch):
    store = SessionStore(sqlite3.connect(":memory:", check_same_thread=False))
    learned.use(store)
    monkeypatch.setattr(inv, "DOCS_HINTS_FILE", inv.DOCS_HINTS_FILE.with_name("missing.yaml"))
    _fake_web(monkeypatch, [result("Usage Limits | Search Console API", "https://developers.google.com/webmaster-tools/limits")])
    findings = inv.investigate(GSC, REQUEST, [])
    feasibility = {"sources": [{"source": GSC, "recommendation": None}]}
    learned.learn({"request_id": "REQ-1", "feasibility": feasibility, "research": {GSC: findings}})
    assert [r["url"] for r in store.source_docs(GSC)] == ["https://developers.google.com/webmaster-tools/limits"]
    # Next request, nothing found by the search engines: the learned link is still there.
    monkeypatch.setattr(config, "RESEARCH_CACHE_DAYS", 0)
    _fake_web(monkeypatch, [])
    again = inv.investigate(GSC, REQUEST, [])
    assert again["links"][0]["found_for"] == ["approved before (1x)"]


def test_a_short_good_list_is_topped_up_from_the_next_engine(monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "http://searxng")
    monkeypatch.setattr(engines._limiter, "execute", lambda run: run())
    monkeypatch.setattr(engines.browser, "available", lambda: False)

    def engine(urls):
        return lambda query, n, timeout: [result("appsflyer api export", u, "appsflyer api") for u in urls]

    monkeypatch.setattr(engines, "ENGINES", [("SearXNG", engine(["https://a/1", "https://a/2"]), False),
                                             ("DuckDuckGo (ddgs)", engine(["https://a/2", "https://b/3"]), False)])
    response = engines.search("appsflyer api export", 8)
    assert [r.url for r in response.results] == ["https://a/1", "https://a/2", "https://b/3"]
    assert response.engine == "SearXNG + DuckDuckGo (ddgs)"
