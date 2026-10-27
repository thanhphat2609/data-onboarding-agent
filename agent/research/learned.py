"""Docs links learned from approved requests, so the next request for a source starts from them.

When the Data Team approves a request, the top links of each source it researched are stored in the
`source_docs` table (agent/workflow/sessions.py), keyed by the source name as searched ("google search console").
The next research for that source reads them first and always lists them, like docs_hints.yaml, but nobody has to
keep a list: the links come from real requests, and only from approved ones. The most often approved come first.

The runner hands its SessionStore over with use(); without one (scripts, tests) nothing is learned or read.
"""
import logging

log = logging.getLogger(__name__)

MAX_LINKS = 5  # learned links read per source
_store = None


def use(store) -> None:
    global _store
    _store = store


def links(source: str) -> list[dict]:
    """[{"url", "title", "approved"}] for the source, most often approved first; [] without a store."""
    if _store is None:
        return []
    try:
        return _store.source_docs(source, MAX_LINKS)
    except Exception as exc:  # noqa: BLE001  research must never fail on this
        log.warning("Could not read learned docs for %s: %s", source, exc)
        return []


def learn(state: dict) -> None:
    """Store the top links of every source researched in an approved request (called once it is done)."""
    if _store is None:
        return
    from agent.workflow.nodes.draft_us import current_research

    for findings in current_research(state).values():
        source = findings.get("search_name") or findings.get("source")
        for link in findings.get("links") or []:
            if "no search result, try this search" in (link.get("found_for") or []):
                continue  # the ready-made search link isn't a doc
            try:
                _store.learn_source_doc(source, link["url"], link.get("title") or link["url"], state.get("request_id", ""))
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not store learned doc %s: %s", link.get("url"), exc)
