"""Pause for the requester to check the draft before it goes to the Data Team.
Resume with {"action": "approve"} or {"action": "edit", "comment": "..."}; a plain string is "approve" when it
is a yes-word ("ok", "approve"), otherwise a change."""
from langgraph.types import interrupt

from agent.workflow.extraction import is_yes
from agent.workflow.nodes.draft_us import draft_preview


def requester_review(state: dict) -> dict:
    """Shows the requester the draft (interrupt). Approval moves on; a comment goes back to intake as a change."""
    decision = interrupt(
        {
            "type": "draft",
            "request_id": state["request_id"],
            "request": state["request"],
            "feasibility": state["feasibility"],
            "research": state.get("research") or {},
            "draft": draft_preview(state),
        }
    )
    if isinstance(decision, str):
        decision = {"action": "approve"} if is_yes(decision) else {"action": "edit", "comment": decision}
    if decision.get("action") == "approve":
        return {"draft_approved": True}
    # A change: back to intake as a user message, like a Data Team edit; a new draft follows.
    return {
        "draft_approved": False,
        "messages": [{"role": "user", "content": (decision.get("comment") or "").strip()}],
        "asked": {"kind": "review"},
    }
