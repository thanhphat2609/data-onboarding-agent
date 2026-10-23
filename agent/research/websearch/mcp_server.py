"""MCP server with the three tools of web-search-mcp, on the Python port (stdio transport).

    python -m agent.research.websearch.mcp_server

MCP client config (LM Studio, Claude Desktop, LibreChat…), run from the agent repo root:

    {"mcpServers": {"web-search": {"command": "python", "args": ["-m", "agent.research.websearch.mcp_server"],
                                   "cwd": "/path/to/data-onboarding-agent"}}}

Tool names, parameters and the text format of the answers follow the original (src/index.ts).
"""
import anyio
from mcp.server.mcpserver import MCPServer

from agent.research import websearch

server = MCPServer("web-search-mcp", version="0.1.0-python")


def _limit(value: int) -> int:
    if not 1 <= int(value) <= 10:
        raise ValueError("Invalid limit: must be a number between 1 and 10")
    return int(value)


def _truncate(text: str, max_length: int | None) -> str:
    if max_length and max_length > 0 and len(text) > max_length:
        return text[:max_length] + f"\n\n[Content truncated at {max_length} characters]"
    return text


@server.tool(
    name="full-web-search",
    description=(
        "Search the web and fetch complete page content from top results. This is the most comprehensive web "
        "search tool. It searches the web and then follows the resulting links to extract their full page content, "
        "providing the most detailed and complete information available. Use get-web-search-summaries for a "
        "lightweight alternative."
    ),
)
async def full_web_search(query: str, limit: int = 5, include_content: bool = True, max_content_length: int | None = None) -> str:
    """limit: number of results with full content (1-10). max_content_length: characters per result, 0 = no limit."""
    result = await anyio.to_thread.run_sync(websearch.full_search, query, _limit(limit), include_content)
    lines = [f'Search completed for "{query}" with {len(result["results"])} results:\n', f"**Status:** {result['status']}\n"]
    for i, r in enumerate(result["results"], 1):
        lines += [f"**{i}. {r.title}**", f"URL: {r.url}", f"Description: {r.description}"]
        if r.full_content.strip():
            lines.append(f"\n**Full Content:**\n{_truncate(r.full_content, max_content_length)}")
        elif r.fetch_status == "error" and include_content:
            lines.append(f"\n**Content Extraction Failed:** {r.error}")
        lines.append("\n---\n")
    return "\n".join(lines)


@server.tool(
    name="get-web-search-summaries",
    description=(
        "Search the web and return only the search result snippets/descriptions without following links to "
        "extract full page content. This is a lightweight alternative to full-web-search for when you only need "
        "brief search results."
    ),
)
async def get_web_search_summaries(query: str, limit: int = 5) -> str:
    """limit: number of search results to return (1-10)."""
    response = await anyio.to_thread.run_sync(websearch.search, query, _limit(limit))
    lines = [f'Search summaries for "{query}" with {len(response.results)} results:\n']
    for i, r in enumerate(response.results[:limit], 1):
        lines += [f"**{i}. {r.title}**", f"URL: {r.url}", f"Description: {r.description}", "\n---\n"]
    return "\n".join(lines)


@server.tool(
    name="get-single-web-page-content",
    description=(
        "Extract and return the full content from a single web page URL. This tool follows a provided URL and "
        "extracts the main page content. Useful for getting detailed content from a specific webpage without "
        "performing a search."
    ),
)
async def get_single_web_page_content(url: str, max_content_length: int | None = None) -> str:
    """max_content_length: characters for the extracted content, 0 = no limit."""
    page = await anyio.to_thread.run_sync(websearch.fetch, url)
    if page.fetch_status != "success":
        return f"**Failed to extract content from: {url}**\n\nError: {page.error}"
    content = page.content
    header = [
        f"**Page Content from: {url}**\n",
        f"**Title:** {page.title}",
        f"**Word Count:** {page.word_count}",
        f"**Content Length:** {len(content)} characters\n",
    ]
    if max_content_length and 0 < max_content_length < len(content):
        body = f"**Content (truncated at {max_content_length} characters):**\n{_truncate(content, max_content_length)}"
    else:
        body = f"**Content:**\n{content}"
    return "\n".join(header) + "\n" + body


if __name__ == "__main__":
    server.run("stdio")
