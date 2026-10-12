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
    "dataset_description": "Bạn cần data gì và dùng cho việc gì?",
    "sources": "Data lấy từ nguồn nào? (GA4, GSC, AppsFlyer, CM, GAM, DV360, DataForSEO, khác)",
    "date_range": "Cần data từ ngày nào đến ngày nào? (vd. 2025-01-01 đến nay)",
    "eta": "Ngày cần data go live (ETA)? (YYYY-MM-DD)",
    "refresh_frequency": "Tần suất cập nhật: daily / hourly / weekly / one-off?",
    "grain": "Mức chi tiết (grain) cần là gì? (vd. ngày x campaign, user, page…)",
    "consumers": "Ai dùng data này và dùng ở đâu? (dashboard, report…)",
}

KNOWN_SOURCES = ["ga4", "gsc", "appsflyer", "cm", "gam", "dv360", "dataforseo"]
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
    approved: bool
    review_comment: str
    outputs: dict[str, Any]
