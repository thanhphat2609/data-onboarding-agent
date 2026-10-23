"""Web research for a source the platform can't onboard yet: find its docs, read them, draft notes + questions.

Finding and reading pages (no API key needed), with agent/research/websearch (port of web-search-mcp):
  A. Links the requester pasted in the chat.
  B. Then a web search (Bing/Brave in a headless browser if available, then DuckDuckGo).
  Pages are read over HTTP, or in the headless browser when they need JavaScript.
Only the source name and fixed keywords leave the machine, never the request text.

Findings are UNVERIFIED. They never change the feasibility decision; they go into the User Story
and the Teams summary as research + questions for the Data Team to confirm.
"""
import logging
import re
from urllib.parse import urlparse

import yaml

from agent import config
from agent.workflow.extraction import norm
from agent.llm.client import get_llm, load_prompt, safe_call
from agent.research import websearch

log = logging.getLogger(__name__)

MAX_PASSAGE_CHARS = 2000  # per page, keeps the LLM prompt small enough for a 7B model
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
# Results from these hosts are opinions/videos, not documentation.
SKIP_HOSTS = ("youtube.", "reddit.", "facebook.", "linkedin.", "quora.", "twitter.", "x.com", "instagram.", "tiktok.com/@")
DOC_HINTS = ("docs", "developer", "developers", "api", "help", "support")

TOPICS = {
    "history": ["retention", "retain", "historical", "history", "backfill", "lookback", "look back", "older than", "stored for"],
    "limits": ["rate limit", "quota", "requests per", "qps", "throttl"],
    "auth": ["oauth", "access token", "api key", "service account", "authenticat", "permission"],
    "access": ["export", "reporting api", "report api", "endpoint", "bigquery", "s3", "sftp", "granularity", "dimensions", "metrics"],
}
NUMBER_UNIT_RE = re.compile(r"\b\d+\s*(?:day|month|year)s?\b", re.I)


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


def search_links(source: str, max_results: int) -> tuple[list[str], str | None]:
    """Web search, no key. Returns (urls, error)."""
    queries = [f"{source} API documentation reporting data", f"{source} API data retention historical data limit"]
    urls: list[str] = []
    errors: list[str] = []
    for q in queries:
        try:
            urls += [r.url for r in websearch.search(q, 6).results]
        except Exception as exc:  # noqa: BLE001 — key-less search can fail or be rate-limited: just "no results"
            log.warning("Web search failed for %s: %s", source, exc)
            errors.append(str(exc))
    if not urls:
        return [], "web search found nothing" + (f" ({errors[0]})" if errors else " (search engines may be rate-limiting this network)")
    urls = [u for u in dict.fromkeys(urls) if not any(h in u.lower() for h in SKIP_HOSTS)]
    urls.sort(key=_rank, reverse=True)  # stable: keeps search order among equally ranked results
    return urls[:max_results], None


# ---------- reading pages ----------

def fetch_page(url: str) -> dict:
    """Read one page and return {"url", "title", "text", "via"} or {"url", "error"}."""
    page = websearch.fetch(url, timeout=15)
    if page.fetch_status != "success":
        return {"url": url, "error": page.error}
    return {"url": url, "title": page.title or url, "text": page.content, "via": page.via}


def passages(text: str) -> list[dict]:
    """Sentences that mention a research topic, tagged with the topic."""
    out, seen, total = [], set(), 0
    for line in text.split("\n"):
        for sent in re.split(r"(?<=[.!?])\s+", line):
            s = sent.strip()
            low = s.lower()
            if not 30 <= len(s) <= 500 or low in seen:
                continue
            topic = next((t for t, words in TOPICS.items() if any(w in low for w in words)), None)
            if not topic:
                continue
            seen.add(low)
            out.append({"topic": topic, "text": s, "has_number": bool(NUMBER_UNIT_RE.search(s))})
            total += len(s)
            if total > MAX_PASSAGE_CHARS:
                return out
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
    body = "\n\n".join(
        f"[{i}] {p['url']}\n" + "\n".join(f"- {x['text']}" for x in p["passages"]) for i, p in enumerate(read, 1)
    )
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


def investigate(source: str, request: dict, messages: list[dict]) -> dict:
    """Research one source. Never raises: network problems end up in `notes`."""
    findings = {"source": source, "pages": [], "pages_read": 0, "key_passages": [], "summary": "", "access_methods": [], "notes": []}
    if config.WEB_RESEARCH:
        candidates = [(u, "requester") for u in links_from_messages(messages, source, request.get("sources", []))]
        if len(candidates) < config.RESEARCH_MAX_PAGES:
            found, err = search_links(source, config.RESEARCH_MAX_PAGES)
            candidates += [(u, "web search") for u in found]
            if err:
                findings["notes"].append(err)
        seen = set()
        for url, origin in candidates:
            if url in seen or len(seen) >= config.RESEARCH_MAX_PAGES:
                continue
            seen.add(url)
            page = {**fetch_page(url), "origin": origin}
            page["passages"] = passages(page.pop("text", "")) if not page.get("error") else []
            findings["pages"].append(page)
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
