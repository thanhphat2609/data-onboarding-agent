"""Result types (ported from web-search-mcp src/types.ts)."""
from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    description: str = "No description available"


@dataclass
class SearchResponse:
    query: str
    engine: str                    # which engine produced the results, "None" if all failed
    results: list[SearchResult]


@dataclass
class Page:
    url: str
    title: str = ""
    content: str = ""
    fetch_status: str = "success"
    error: str = ""
    via: str = "http"

    @property
    def word_count(self) -> int:
        return len(self.content.split())
