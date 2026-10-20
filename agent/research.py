"""Web research for a source that has no playbook: find its docs, read them, draft a playbook + questions.

Finding pages (no API key needed):
  A. Known doc links: `doc_links.yaml` (kept by the team) + links the requester pasted in the chat.
  B. Fallback: a DuckDuckGo search (`ddgs` package — unofficial, may be rate-limited or break).
Only the source name and fixed keywords leave the machine, never the request text.

Findings are UNVERIFIED. They never change the feasibility decision; they go into the User Story
and the Teams summary as research + questions for the Data Team to confirm.
"""
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
import yaml

from agent import config
from agent.extraction import norm
from agent.llm import get_llm, load_prompt, safe_call

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; data-onboarding-agent/0.1; +internal prototype)"
MAX_PAGE_BYTES = 2_000_000
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

def known_links(source: str) -> list[str]:
    """Doc links the team listed for this source in doc_links.yaml."""
    if not config.DOC_LINKS_PATH.exists():
        return []
    data = yaml.safe_load(config.DOC_LINKS_PATH.read_text(encoding="utf-8")) or {}
    links = {slug(k): v for k, v in data.items()}.get(slug(source)) or []
    return [str(u) for u in links]


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
    """DuckDuckGo search, no key. Returns (urls, error)."""
    try:
        from ddgs import DDGS
    except ImportError:
        return [], "web search unavailable (`ddgs` package not installed)"
    queries = [f"{source} API documentation reporting data", f"{source} API data retention historical data limit"]
    urls: list[str] = []
    try:
        ddgs = DDGS(timeout=15)
        for q in queries:
            urls += [r["href"] for r in ddgs.text(q, max_results=6) if r.get("href")]
    except Exception as exc:  # noqa: BLE001 — unofficial scraper: any failure just means "no results"
        log.warning("Web search failed for %s: %s", source, exc)
        if not urls:
            return [], f"web search failed: {exc}"
    urls = [u for u in dict.fromkeys(urls) if not any(h in u.lower() for h in SKIP_HOSTS)]
    urls.sort(key=_rank, reverse=True)  # stable: keeps search order among equally ranked results
    return urls[:max_results], None


# ---------- reading pages ----------

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe", "head"}
    BLOCK = {"p", "div", "li", "br", "tr", "section", "article", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "table", "dd", "dt"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data.replace("\n", " "))  # line breaks in the HTML source are not paragraph breaks

    def text(self) -> str:
        lines = (re.sub(r"\s+", " ", ln).strip() for ln in "".join(self.parts).split("\n"))
        return "\n".join(ln for ln in lines if ln)


def fetch_page(url: str) -> dict:
    """Download one page and return {"url", "title", "text"} or {"url", "error"}."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15, stream=True)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype and "text" not in ctype:
            return {"url": url, "error": f"not a web page ({ctype or 'unknown type'})"}
        raw = resp.raw.read(MAX_PAGE_BYTES, decode_content=True)
        html = raw.decode(resp.encoding or "utf-8", errors="replace")
    except requests.RequestException as exc:
        return {"url": url, "error": str(exc)}
    if "html" not in ctype:
        return {"url": url, "title": url, "text": html}
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.text()
    page = {"url": url, "title": parser.title.strip() or url, "text": text}
    if len(text) < 500:
        page["error"] = "page has almost no text — it probably needs JavaScript to render"
    return page


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


def draft_playbook(source: str, findings: dict) -> str:
    """Playbook skeleton in the same format as playbooks/*.yaml, every value to be checked by the team."""
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
        "current_connector": "TODO",
        "existing_models": [],
        "owner": "TODO",
        "notes": "",
        "research_sources": [p["url"] for p in findings["pages"] if not p.get("error")],
    }
    header = (
        f"# DRAFT written by the agent from web research — UNVERIFIED.\n"
        f"# Check every value against the docs and our account, set review_status: reviewed,\n"
        f"# then save it as playbooks/{slug(source)}.yaml.\n"
    )
    return header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def investigate(source: str, request: dict, messages: list[dict]) -> dict:
    """Research one source. Never raises: network problems end up in `notes`."""
    findings = {"source": source, "pages": [], "pages_read": 0, "key_passages": [], "summary": "", "access_methods": [], "notes": []}
    if config.WEB_RESEARCH:
        candidates = [(u, "requester") for u in links_from_messages(messages, source, request.get("sources", []))]
        candidates += [(u, "doc_links.yaml") for u in known_links(source)]
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
