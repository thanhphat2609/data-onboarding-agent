"""Web research for a source the platform can't onboard yet: find its docs, read them, draft notes + questions.

Research runs in rounds, like a person (or Claude) researching instead of a single search:
  1. Plan: one search per topic (access/export, history/retention, limits, auth) plus the official docs.
     Links the requester pasted are read first.
  2. Prefer primary sources: the source's own docs site (the doc-like host found most often, preferring one
     that carries the source's name) ranks first.
  3. Read the best pages and keep the most useful sentences per page (numbers first, every topic represented).
  4. Find gaps: topics with no evidence yet (or history without a number) get follow-up searches on the docs
     site (`site:<docs host> …`), until RESEARCH_ROUNDS, RESEARCH_MAX_PAGES or RESEARCH_TIME_BUDGET_S runs out.
  5. Show the work: every query is kept in findings["searches"] and listed in the User Story.
  6. Top links: the TOP_LINKS most relevant links from every search, read or not, so the team always has a place
     to start even when reading or summarising the pages fails.
Known official docs (docs_hints.yaml) are read first and always listed, whatever the search engines return.
A result counts only when its title or URL names the source (Google Analytics pages don't count for Google Search
Console), and a page whose text never names it gives no passages. Search results and pages are cached for
RESEARCH_CACHE_DAYS (agent/research/cache.py), so asking about the same source again gives the same links.
Everything goes through two tools, web_search and web_fetch (agent/research/websearch, no API key).
Only the source name (plus its vendor, when the requester named a known one as the origin) and fixed keywords
leave the machine, never the request text.

Findings are UNVERIFIED. They never change the feasibility decision; they go into the User Story
and the Teams summary as research + questions for the Data Team to confirm.
"""
import logging
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import yaml

from agent import config
from agent.research import cache
from agent.workflow.extraction import VENDOR_PRODUCTS, norm
from agent.llm.client import get_llm, load_prompt, safe_call
from agent.research import websearch

log = logging.getLogger(__name__)

MAX_PASSAGE_CHARS = 4000  # per page: the most useful sentences, not the first ones
LLM_MAX_CHARS = 9000  # all passages sent to the LLM together, small enough for a 7B model's context
TOP_LINKS = 5  # links listed per source in the User Story, the review panel and the Teams summary
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
# Results from these hosts are opinions/videos, not documentation.
SKIP_HOSTS = ("youtube.", "reddit.", "facebook.", "linkedin.", "quora.", "twitter.", "x.com", "instagram.", "tiktok.com/@")
DOC_HINTS = ("docs", "developer", "developers", "api", "help", "support")

TOPICS = {
    # Not "history" / "historical" alone: analytics docs use them for other things ("historical audience membership").
    "history": ["retention", "retain", "historical data", "data history", "backfill", "lookback", "look back",
                "older than", "stored for", "months of data", "days of data", "years of data"],
    "limits": ["rate limit", "quota", "requests per", "qps", "throttl"],
    "auth": ["oauth", "access token", "api key", "service account", "authenticat", "permission"],
    "access": ["export", "reporting api", "report api", "endpoint", "bigquery", "s3", "sftp", "granularity", "dimensions", "metrics"],
}
NUMBER_UNIT_RE = re.compile(r"\b\d+\s*(?:day|month|year)s?\b", re.I)
# "data from the last 16 months", "keeps 14 months of data", "available for 90 days": history with a number.
HISTORY_RE = re.compile(
    r"\b\d+\s*(?:day|month|year)s?\b.{0,40}\b(?:data|history|available|stored|kept|retained)\b"
    r"|\b(?:data|history|available|stored|kept|retained|keeps?|stores?)\b.{0,40}\b\d+\s*(?:day|month|year)s?\b",
    re.I,
)
DOCS_HINTS_FILE = Path(__file__).with_name("docs_hints.yaml")

# Round 1: one search per topic plus the official docs. Fixed words only: the request text never leaves the machine.
# {source} is the plain source name (google search console). Not an exact phrase: quoted queries often get no
# results at all; results that drift to other products are dropped by _about_source instead.
DOCS_QUERY = "{source} developer documentation"
TOPIC_QUERIES = {
    "access": "{source} API export data documentation",
    "history": "{source} data retention how far back historical data",
    "limits": "{source} API rate limits quota",
    "auth": "{source} API authentication access",
}
# Later rounds: what to look for on the docs site for a topic that still has no evidence.
FOLLOW_UP = {
    "access": "export API reporting data",
    "history": "data retention historical data",
    "limits": "rate limits quotas",
    "auth": "authentication OAuth API key",
}


def slug(source: str) -> str:
    return re.sub(r"[^\w]+", "_", norm(source)).strip("_")


# ---------- finding pages ----------

def links_from_messages(messages: list[dict], source: str, all_sources: list[str]) -> list[str]:
    """Links the requester pasted. A link that names a source goes to that source; others go to every source."""
    urls = [u.rstrip(".,;") for m in messages if m.get("role") == "user" for u in URL_RE.findall(m.get("content", ""))]
    tokens = {s: [t for t in slug(s).split("_") if len(t) > 2] for s in all_sources}
    out = []
    for u in urls:
        owners = [s for s, toks in tokens.items() if any(t in u.lower() for t in toks)]
        if not owners or source in owners:
            out.append(u)
    return list(dict.fromkeys(out))


def _rank(url: str) -> int:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    return sum(h in host for h in DOC_HINTS) * 2 + sum(f"/{h}" in path for h in DOC_HINTS)


def search_name(source: str, origin: str = "") -> str:
    """The source name as searched: "search console" from "Google" -> "google search console". Only a known
    vendor name is taken from the origin answer, so the requester's own words stay on this machine."""
    name = norm(source)
    vendor = next((v for v in VENDOR_PRODUCTS if re.search(rf"\b{v}\b", norm(origin or ""))), None)
    return f"{vendor} {name}" if vendor and not re.search(rf"\b{vendor}\b", name) else name


def _source_words(source: str) -> list[str]:
    return [t for t in slug(source).split("_") if len(t) > 2] or [slug(source)]


def _words_text(text: str) -> str:
    """Lowercase words separated by single spaces, padded: search-console in a URL reads as " search console "."""
    return " " + " ".join(re.sub(r"[^\w]+", " ", text.lower()).split()) + " "


def _core_phrase(source: str) -> str:
    """The source name without its vendor: "search console" for "google search console" (a vendor name alone
    matches every product of that vendor)."""
    words = _source_words(source)
    return " ".join([w for w in words if w not in VENDOR_PRODUCTS] or words)


def _has_phrase(text: str, phrase: str) -> bool:
    """The phrase's words in order in `text` (from _words_text), allowing up to two short words between them:
    "erp postgresql" matches "erp on postgresql"."""
    gap = r"(?: \w{1,3}){0,2} "
    return re.search(" " + gap.join(map(re.escape, phrase.split())) + " ", text) is not None


def _about_source(result, words: list[str]) -> bool:
    """A result is on topic when its title or URL names the source as a phrase ("search console", vendor aside)
    and every word of the source appears in its title, URL or description. Being mentioned only in the
    description isn't enough: Google Analytics pages often mention Search Console there."""
    title_url = _words_text(f"{result.title} {result.url}")
    everything = _words_text(f"{result.title} {result.description} {result.url}")
    return _has_phrase(title_url, _core_phrase(" ".join(words))) and all(f" {w} " in everything for w in words)


def _names_source(text: str, source: str) -> bool:
    """A page is about the source when its text names it at least once (vendor aside)."""
    return _has_phrase(_words_text(text), _core_phrase(source))


def known_docs(source: str) -> list[str]:
    """Official docs listed for the source in docs_hints.yaml (by name, or by an alias), else []."""
    try:
        hints = yaml.safe_load(DOCS_HINTS_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        log.warning("Could not read %s: %s", DOCS_HINTS_FILE, exc)
        return []
    name = " ".join(_source_words(source))
    for key, entry in hints.items():
        names = {" ".join(_source_words(n)) for n in [key, *((entry or {}).get("aliases") or [])]}
        if name in names or _core_phrase(source) in names:
            return list((entry or {}).get("urls") or [])
    return []


def _cached_search(query: str, n: int) -> tuple[list, bool]:
    """(results, from cache). Results are websearch SearchResult objects."""
    hit = cache.get("search", f"{n}|{query}")
    if hit is not None:
        return [websearch.SearchResult(**r) for r in hit], True
    results = websearch.web_search(query, n).results
    if results:
        cache.put("search", f"{n}|{query}", [{"title": r.title, "url": r.url, "description": r.description} for r in results])
    return results, False


def _search(query: str, source: str, findings: dict, round_no: int, errors: list[str], topic: str, hits: dict,
            n: int = 8) -> list[str]:
    """One web_search, logged in findings["searches"]: kept results are about the source and not a
    forum/video site, and are added to `hits` (url -> title + the topics whose searches found it).
    Failures (rate limits) just mean no results."""
    cached = False
    try:
        results, cached = _cached_search(query, n)
    except Exception as exc:  # noqa: BLE001
        log.warning("Web search failed for %r: %s", query, exc)
        errors.append(str(exc))
        results = []
    words = _source_words(source)
    kept = [r.url for r in results if _about_source(r, words) and not any(h in r.url.lower() for h in SKIP_HOSTS)]
    findings["searches"].append({"round": round_no, "query": query, "results": len(kept),
                                 "off_topic": len(results) - len(kept), "cached": cached})
    titles = {r.url: r.title for r in results}
    for url in kept:
        hit = hits.setdefault(url, {"title": titles[url], "topics": []})
        if topic not in hit["topics"]:
            hit["topics"].append(topic)
    return kept


def _docs_host(urls: list[str], source: str, known: list[str] = ()) -> str | None:
    """The source's own docs site: the host of its known docs, else the doc-like host found most often, preferring
    hosts that carry the source's name (so a connector vendor's page about the source doesn't win)."""
    if known:
        return urlparse(known[0]).netloc.lower()
    tokens = [t for t in slug(source).split("_") if len(t) > 2]
    counts = Counter(urlparse(u).netloc.lower() for u in urls if _rank(u) > 0)
    if not counts:
        return None
    return max(counts, key=lambda h: (any(t in h for t in tokens), counts[h]))


def _priority(url: str, docs_host: str | None) -> int:
    return (urlparse(url).netloc.lower() == docs_host) * 10 + _rank(url)


def _missing_topics(pages: list[dict]) -> list[str]:
    """Topics with no evidence yet; history also counts as missing while no passage gives a number."""
    found = [p for pg in pages for p in pg.get("passages", [])]
    missing = [t for t in TOPICS if not any(p["topic"] == t for p in found)]
    if "history" not in missing and not any(p["topic"] == "history" and p["has_number"] for p in found):
        missing.append("history")
    return missing


def _top_links(source: str, pasted: list[str], hits: dict, pages: list[dict], docs_host: str | None,
               known: list[str] = ()) -> list[dict]:
    """The TOP_LINKS most relevant links, read or not: links the requester pasted first, then by docs site,
    pages with useful sentences, and how many topic searches found the page. With no result at all,
    a ready-made search link, so there is still somewhere to start."""
    read = {p["url"]: p for p in pages if not p.get("error")}
    off_topic = {p["url"] for p in pages if p.get("off_topic")}
    first = list(dict.fromkeys([*pasted, *known]))

    def score(url: str) -> int:
        return _priority(url, docs_host) + 5 * bool(read.get(url, {}).get("passages")) + 3 * len(hits[url]["topics"])

    ranked = sorted((u for u in hits if u not in first and u not in off_topic), key=score, reverse=True)
    links = [{"url": u, "title": read.get(u, {}).get("title") or u,
              "found_for": ["requester" if u in pasted else "known docs"]} for u in first]
    links += [{"url": u, "title": read.get(u, {}).get("title") or hits[u]["title"] or u, "found_for": hits[u]["topics"]}
              for u in ranked]
    if not links:
        query = DOCS_QUERY.format(source=source)
        return [{"url": "https://www.google.com/search?q=" + quote_plus(query), "title": f"Search the web: {query}",
                 "found_for": ["no search result, try this search"]}]
    return links[:TOP_LINKS]


# ---------- reading pages ----------

def fetch_page(url: str) -> dict:
    """Read one page with web_fetch; {"url", "title", "text", "via"} or {"url", "error"}."""
    hit = cache.get("page", url)
    if hit is not None:
        return {**hit, "via": f"{hit.get('via', 'http')}, cached"}
    page = websearch.web_fetch(url, timeout=15)
    if page.fetch_status != "success":
        return {"url": url, "error": page.error}
    result = {"url": url, "title": page.title or url, "text": page.content, "via": page.via}
    cache.put("page", url, result)
    return result


def passages(text: str) -> list[dict]:
    """The most useful sentences that mention a research topic, tagged with the topic: taken in turns per topic,
    sentences with a number (e.g. "14 months") first, up to MAX_PASSAGE_CHARS for the page."""
    by_topic: dict[str, list[dict]] = {t: [] for t in TOPICS}
    seen = set()
    for line in text.split("\n"):
        for sent in re.split(r"(?<=[.!?])\s+", line):
            s = sent.strip()
            low = s.lower()
            if not 30 <= len(s) <= 500 or low in seen:
                continue
            topic = "history" if HISTORY_RE.search(s) else next((t for t, words in TOPICS.items() if any(w in low for w in words)), None)
            if not topic:
                continue
            seen.add(low)
            by_topic[topic].append({"topic": topic, "text": s, "has_number": bool(NUMBER_UNIT_RE.search(s))})
    for cands in by_topic.values():
        cands.sort(key=lambda p: not p["has_number"])  # stable: page order among equals
    out, total = [], 0
    while any(by_topic.values()):
        for cands in by_topic.values():
            if not cands:
                continue
            p = cands.pop(0)
            if total + len(p["text"]) <= MAX_PASSAGE_CHARS:
                out.append(p)
                total += len(p["text"])
    return out


# ---------- putting it together ----------

def _key_passages(pages: list[dict], per_topic: int = 3) -> list[dict]:
    """Most useful passages across pages: history passages with a number first, then the rest."""
    picked = []
    for topic in TOPICS:
        cands = [{**p, "url": pg["url"]} for pg in pages for p in pg.get("passages", []) if p["topic"] == topic]
        cands.sort(key=lambda p: not p["has_number"])
        picked += cands[:per_topic]
    return picked


def _questions(source: str, request: dict, findings: dict) -> list[str]:
    start = (request.get("date_range") or {}).get("start", "?")
    history = [p for p in findings["key_passages"] if p["topic"] == "history" and p["has_number"]]
    qs = [f"Do we already ingest `{source}` anywhere (Fivetran/Airbyte/custom script)? If so, where does it land?"]
    if not findings["pages_read"]:
        qs.append(f"The agent could not read any documentation for `{source}` — can someone share the official API/docs link?")
    if history:
        qs.append(f"Docs say: “{history[0]['text']}” — does this apply to our account, and does it cover the requested start {start}?")
    else:
        qs.append(f"How far back can `{source}` data be pulled? The request needs data from {start}.")
    qs += [
        f"Who owns the `{source}` account, and can the Data Team get API/export access?",
        f"Do API quotas allow a {request.get('refresh_frequency', '?')} refresh at grain `{request.get('grain', '?')}`?",
        f"Is go-live by {request.get('eta', '?')} realistic once access is sorted?",
    ]
    qs += [q for q in findings.get("llm_questions", []) if q not in qs][:3]
    return qs


def _llm_findings(source: str, pages: list[dict]) -> dict:
    llm = get_llm()
    read = [p for p in pages if p.get("passages")]
    if not llm or not read:
        return {}
    # Pages in turns, best passages first, so every page gets a say within LLM_MAX_CHARS.
    lines = {i: [] for i in range(1, len(read) + 1)}
    queues = {i: list(p["passages"]) for i, p in enumerate(read, 1)}
    total = 0
    while any(queues.values()) and total < LLM_MAX_CHARS:
        for i, q in queues.items():
            if q and total < LLM_MAX_CHARS:
                text = q.pop(0)["text"]
                lines[i].append(f"- {text}")
                total += len(text)
    body = "\n\n".join(f"[{i}] {p['url']}\n" + "\n".join(lines[i]) for i, p in enumerate(read, 1) if lines[i])
    gen = safe_call(llm.complete_json, load_prompt("investigate_source"), f"Source: {source}\n\n{body}", default={}) or {}
    urls = {str(i): p["url"] for i, p in enumerate(read, 1)}
    methods = []
    for m in gen.get("access_methods") or []:
        if not isinstance(m, dict) or not m.get("type"):
            continue
        methods.append({**m, "evidence": urls.get(str(m.get("evidence", "")).strip("[] "), m.get("evidence"))})
    return {
        "summary": str(gen.get("summary") or "").strip(),
        "access_methods": methods,
        "llm_questions": [str(q) for q in (gen.get("open_questions") or []) if q][:3],
    }


def draft_source_notes(source: str, findings: dict) -> str:
    """Notes for onboarding the source (access methods, limits, docs), every value to be checked by the team."""
    methods = [
        {
            "type": m.get("type"),
            "available_from": m.get("available_from"),
            "max_lookback_days": m.get("max_lookback_days"),
            "typical_lead_time_days": None,
            "notes": f"UNVERIFIED (web research): {m.get('notes', '')} — source: {m.get('evidence', '?')}".strip(),
        }
        for m in findings.get("access_methods", [])
    ] or [{"type": "TODO", "available_from": None, "max_lookback_days": None, "typical_lead_time_days": None, "notes": "TODO"}]
    data = {
        "source": slug(source),
        "display_name": source,
        "review_status": "draft",
        "access_methods": methods,
        "owner": "TODO",
        "notes": "",
        "research_sources": [p["url"] for p in findings["pages"] if not p.get("error")],
    }
    header = (
        "# DRAFT written by the agent from web research — UNVERIFIED.\n"
        "# Check every value against the docs and our account. To onboard the source, the platform needs\n"
        "# a source template in data-onboarding-ingestion (code/templates/sources/).\n"
    )
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _research(source: str, request: dict, messages: list[dict], findings: dict) -> None:
    """The rounds described in the module docstring; fills findings["pages"], ["searches"], ["docs_site"], ["rounds"]."""
    started = time.monotonic()
    errors: list[str] = []
    seen: set[str] = set()
    hits: dict[str, dict] = {}

    def time_left() -> bool:
        return time.monotonic() - started < config.RESEARCH_TIME_BUDGET_S

    name = search_name(source, request.get("source_origin", ""))
    pasted = links_from_messages(messages, source, request.get("sources", []))
    known = [u for u in known_docs(name) if u not in pasted]
    findings["known_docs"] = known
    max_pages = config.RESEARCH_MAX_PAGES + len(known)  # known docs come on top of the searches' pages

    def read(candidates: list[tuple[str, str]], limit: int, round_no: int) -> None:
        for url, origin in candidates:
            if limit <= 0 or len(seen) >= max_pages or not time_left():
                return
            if url in seen:
                continue
            seen.add(url)
            limit -= 1
            page = {**fetch_page(url), "origin": origin, "round": round_no}
            text = page.pop("text", "")
            # A search result whose page never names the source (a menu link, another product) gives nothing.
            if not page.get("error") and origin.endswith("search") and not _names_source(text, name):
                page["off_topic"] = True
                text = ""
            page["passages"] = passages(text) if not page.get("error") else []
            findings["pages"].append(page)

    # Round 1: plan one search per topic, read the best pages; keep some page budget for the follow-ups.
    found: list[str] = []
    for topic, query in [("docs", DOCS_QUERY), *TOPIC_QUERIES.items()]:
        if time_left():
            found += _search(query.format(source=name), name, findings, 1, errors, topic, hits)
    found = list(dict.fromkeys(found))
    docs_host = _docs_host(found, source, known)
    findings["docs_site"] = docs_host
    found.sort(key=lambda u: _priority(u, docs_host), reverse=True)  # stable: search order among equals
    first_round = max(3, config.RESEARCH_MAX_PAGES // 2) if config.RESEARCH_ROUNDS > 1 else config.RESEARCH_MAX_PAGES
    first_round += len(known)  # known docs don't take the searches' share of the pages
    read([(u, "requester") for u in pasted] + [(u, "known docs") for u in known] + [(u, "web search") for u in found],
         first_round, 1)
    findings["rounds"] = 1

    # Later rounds: search again, on the docs site, only for what is still missing.
    for round_no in range(2, config.RESEARCH_ROUNDS + 1):
        missing = _missing_topics(findings["pages"])
        if not missing or len(seen) >= max_pages or not time_left():
            break
        more: list[str] = []
        for topic in missing:
            # The source name stays in: a docs host like developers.google.com covers many products.
            query = f"site:{docs_host} {name} {FOLLOW_UP[topic]}" if docs_host else f"{name} {FOLLOW_UP[topic]} documentation"
            if time_left():
                more += _search(query, name, findings, round_no, errors, topic, hits)
        more = sorted(dict.fromkeys(more), key=lambda u: _priority(u, docs_host), reverse=True)
        read([(u, "follow-up search") for u in more], 2 * len(missing), round_no)
        findings["rounds"] = round_no

    findings["links"] = _top_links(name, pasted, hits, findings["pages"], docs_host, known)
    if not found and not pasted and not known and not any(s["results"] for s in findings["searches"]):
        off_topic = sum(s.get("off_topic", 0) for s in findings["searches"])
        if off_topic:
            findings["notes"].append(
                f"web search returned {off_topic} result(s), but none named `{name}`: check the source name"
            )
        else:
            findings["notes"].append(
                "web search found nothing" + (f" ({errors[0]})" if errors else " (search engines may be rate-limiting this network)")
            )
    if not time_left():
        findings["notes"].append(f"research stopped at the time budget ({config.RESEARCH_TIME_BUDGET_S} s)")
    if missing := _missing_topics(findings["pages"]):
        findings["notes"].append("no evidence found for: " + ", ".join(missing))


def investigate(source: str, request: dict, messages: list[dict]) -> dict:
    """Research one source. Never raises: network problems end up in `notes`."""
    findings = {
        "source": source, "pages": [], "pages_read": 0, "key_passages": [], "summary": "", "access_methods": [],
        "notes": [], "searches": [], "docs_site": None, "rounds": 0, "links": [], "known_docs": [],
    }
    if config.WEB_RESEARCH:
        _research(source, request, messages, findings)
        findings["pages_read"] = sum(1 for p in findings["pages"] if p["passages"])
        findings["key_passages"] = _key_passages(findings["pages"])
        findings.update(_llm_findings(source, findings["pages"]))
    else:
        findings["notes"].append("web research is turned off (WEB_RESEARCH=0)")
    findings["questions"] = _questions(source, request, findings)
    findings.pop("llm_questions", None)
    for p in findings["pages"]:
        p.pop("passages", None)  # kept in key_passages; no need to store every sentence in the checkpoint
    return findings
