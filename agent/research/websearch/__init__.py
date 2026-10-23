"""Web search and page reading without API keys: a Python port of web-search-mcp
(https://github.com/mrkrsl/web-search-mcp, MIT, see LICENSE-web-search-mcp).

    from agent.research import websearch
    websearch.search("GA4 data retention", 5)        # SearchResponse(engine, results)
    websearch.full_search("GA4 data retention", 3)   # results with page content
    websearch.fetch("https://…")                     # Page(title, content, fetch_status, error, via)

Also served as an MCP server with the original's three tools: `python -m agent.research.websearch.mcp_server`.
"""
from agent.research.websearch.engines import search
from agent.research.websearch.content import fetch, fetch_results, is_pdf
from agent.research.websearch.models import Page, SearchResponse, SearchResult

__all__ = ["search", "fetch", "fetch_results", "full_search", "is_pdf", "Page", "SearchResponse", "SearchResult"]


def full_search(query: str, limit: int = 5, include_content: bool = True) -> dict:
    """Search, then fetch the content of the top results (the original's `full-web-search`)."""
    search_limit = min(limit * 2 + 2, 10) if include_content else limit
    response = search(query, search_limit)
    pdfs = sum(is_pdf(r.url) for r in response.results)
    results = fetch_results(response.results, limit) if include_content else response.results[:limit]
    status = f"Search engine: {response.engine}; {limit} result requested/{len(response.results)} obtained; PDF: {pdfs}"
    if include_content:
        ok = sum(r.fetch_status == "success" for r in results)
        status += f"; {len(results)} followed; Successfully extracted: {ok}; Failed: {len(results) - ok}"
    return {"query": query, "engine": response.engine, "status": status, "results": results}
