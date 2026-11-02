"""MCP server with two tools, web_search and web_fetch, on the Python port (stdio transport).

    python -m agent.research.websearch.mcp_server

MCP client config (LM Studio, Claude Desktop, LibreChat…), run from the agent repo root:

    {"mcpServers": {"web-search": {"command": "python", "args": ["-m", "agent.research.websearch.mcp_server"],
                                   "cwd": "/path/to/data-onboarding-agent"}}}

web-search-mcp had three tools (search with page content, search summaries, single page); search + fetch
cover the same ground: search for links, then fetch the pages worth reading.
"""
import anyio
from mcp.server.mcpserver import MCPServer

from agent.research import websearch

server = MCPServer("web-search", version="0.2.0-python")


def _truncate(text: str, max_length: int | None) -> str:
    """Cuts text at ``max_length`` characters and says so."""
    if max_length and max_length > 0 and len(text) > max_length:
        return text[:max_length] + f"\n\n[Content truncated at {max_length} characters]"
    return text


@server.tool(
    name="web_search",
    description=(
        "Search the web and return the top results: title, URL and snippet. No page content; "
        "use web_fetch on the URLs worth reading."
    ),
)
async def web_search(query: str, limit: int = 8) -> str:
    """limit: number of results (1-10)."""
    if not 1 <= int(limit) <= 10:
        raise ValueError("Invalid limit: must be a number between 1 and 10")
    response = await anyio.to_thread.run_sync(websearch.web_search, query, int(limit))
    lines = [f'Search results for "{query}" ({len(response.results)}, engine: {response.engine}):\n']
    for i, r in enumerate(response.results, 1):
        lines += [f"**{i}. {r.title}**", f"URL: {r.url}", f"Description: {r.description}", "\n---\n"]
    return "\n".join(lines)


@server.tool(
    name="web_fetch",
    description="Fetch one web page and return its main text (plain HTTP, headless browser as fallback).",
)
async def web_fetch(url: str, max_content_length: int | None = None) -> str:
    """max_content_length: characters of content to return, 0 = no limit."""
    page = await anyio.to_thread.run_sync(websearch.web_fetch, url)
    if page.fetch_status != "success":
        return f"**Failed to fetch: {url}**\n\nError: {page.error}"
    return "\n".join([
        f"**Page Content from: {url}**\n",
        f"**Title:** {page.title}",
        f"**Word Count:** {page.word_count}\n",
        f"**Content:**\n{_truncate(page.content, max_content_length)}",
    ])


if __name__ == "__main__":
    server.run("stdio")
