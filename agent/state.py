"""Graph state and request schema."""
import operator
from typing import Annotated, Any, TypedDict

REQUIRED_FIELDS = [
    "dataset_description",
    "sources",
    "date_range",
    "eta",
    "refresh_frequency",
    "grain",
    "consumers",
]

FIELD_QUESTIONS = {
    "dataset_description": "What data do you need, and what will it be used for?",
    "sources": "Which source system(s)? (already onboarded: {systems}; or a new system, e.g. \"ERP on PostgreSQL\")",
    "date_range": "What date range? (e.g. from 2025-01-01 to now)",
    "eta": "When does the data need to go live (ETA)? (YYYY-MM-DD, or e.g. \"in 2 weeks\")",
    "refresh_frequency": "Refresh frequency: daily / hourly / weekly / one-off?",
    "grain": "What grain (level of detail)? (e.g. date x campaign, user, page…)",
    "consumers": "Who will use this data, and where? (dashboard, report…)",
}

FREQUENCIES = ["daily", "hourly", "weekly", "one-off"]


class Request(TypedDict, total=False):
    dataset_description: str
    sources: list[str]
    date_range: dict  # {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    eta: str  # "YYYY-MM-DD"
    refresh_frequency: str
    grain: str
    consumers: str


class AgentState(TypedDict, total=False):
    request_id: str
    requested_by: str  # login of the requester ("" when the web UI has no login)
    today: str  # lets old requests be replayed with a simulated "today"
    messages: Annotated[list[dict], operator.add]  # {"role": "user"|"assistant", "content": str}
    n_processed: int  # number of messages already processed by intake
    request: Request
    missing_fields: list[str]
    errors: dict[str, str]
    asked: dict  # {"kind": "fields"|"gap"|"review", "fields": [...]}
    pending_question: str
    intake_turns: int
    thread_ref: str
    existing_models: list[dict]
    feasibility: dict
    gap: list[dict]
    accepted_gaps: list[str]
    research: dict[str, dict]  # source -> web research findings (sources the platform can't onboard yet)
    approved: bool
    review_comment: str
    outputs: dict[str, Any]
