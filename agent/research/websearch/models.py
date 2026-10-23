"""Result types (ported from web-search-mcp src/types.ts)."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SearchResult:
    title: str
    url: str
    description: str = "No description available"
    full_content: str = ""
    content_preview: str = ""
    word_count: int = 0
    timestamp: str = field(default_factory=now_iso)
    fetch_status: str = "success"  # success | error
    error: str = ""
    via: str = ""                  # http | browser, once content was fetched

    def to_dict(self) -> dict:
        return asdict(self)


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
