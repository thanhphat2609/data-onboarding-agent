"""Pause for human review. Resume with {"action": "approve"} or {"action": "edit", "comment": "..."}."""
from langgraph.types import interrupt

from agent.workflow.extraction import is_yes


def approval(state: dict) -> dict:
    """Waits for the Data Team (interrupt). Approval moves on; a comment goes back to intake as a change."""
    decision = interrupt(
        {
            "type": "approval",
            "request_id": state["request_id"],
            "request": state["request"],
            "existing_models": [m["name"] for m in state.get("existing_models") or []],
            "feasibility": state["feasibility"],
            "research": state.get("research") or {},
        }
    )
    if isinstance(decision, str):
        decision = {"action": "approve", "comment": ""} if is_yes(decision) else {"action": "edit", "comment": decision}

    comment = (decision.get("comment") or "").strip()
    if decision.get("action") == "approve":
        return {"approved": True, "review_comment": comment}
    # Edit: send the comment back to intake as a user message so it updates the request
    return {
        "approved": False,
        "review_comment": comment,
        "messages": [{"role": "user", "content": comment}],
        "asked": {"kind": "review"},
    }
