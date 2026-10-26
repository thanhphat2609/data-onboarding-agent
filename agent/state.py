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
    "sources": "Which dataset or product is it? Its exact name (already onboarded: {systems}; or a new one, "
               "e.g. \"Google Search Console\", \"ERP on PostgreSQL\")",
    # Asked only for sources the platform can't onboard yet (agent/workflow/nodes/intake.py), not one of the 7 details.
    "source_origin": "Where does {new_sources} come from? The vendor/app and how the data is reached (API, database, "
                     "file export…). Paste a link to its docs if you have one.",
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
    source_origin: str  # where sources the platform can't onboard yet come from, in the requester's words


class AgentState(TypedDict, total=False):
    request_id: str
    requested_by: str  # business owner of the request: a login ("" when the web UI has no login)
    created_by: str  # login that typed it; differs from requested_by when the Data Team files it on someone's behalf
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
    draft_approved: bool  # the requester approved the draft (requester_review); then it goes to the Data Team
    approved: bool
    review_comment: str
    outputs: dict[str, Any]
