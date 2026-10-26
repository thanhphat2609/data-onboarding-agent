"""Web search and page reading without API keys: a Python port of web-search-mcp
(https://github.com/mrkrsl/web-search-mcp, MIT, see LICENSE-web-search-mcp), cut down to two tools.

    from agent.research import websearch
    websearch.web_search("google search console data retention", 8)   # SearchResponse(engine, results)
    websearch.web_fetch("https://…")                                  # Page(title, content, fetch_status, error, via)

Also served as an MCP server with the same two tools: `python -m agent.research.websearch.mcp_server`.
"""
from agent.research.websearch.engines import search as web_search
from agent.research.websearch.content import fetch as web_fetch
from agent.research.websearch.models import Page, SearchResponse, SearchResult

__all__ = ["web_search", "web_fetch", "Page", "SearchResponse", "SearchResult"]
