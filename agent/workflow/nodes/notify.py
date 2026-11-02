"""Notify the Data Team about a new request once the requester approved its draft (sent once per request)."""
import json

from agent.integrations import teams
from agent.workflow.nodes.common import format_request, output_dir


def notify(state: dict) -> dict:
    """Posts the request to the Data Team's Teams channel once; returns the thread reference."""
    if state.get("thread_ref"):
        return {}
    request = state["request"]
    out = output_dir(state)
    (out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    text = format_request(request) + (
        f"\n\n**Feasibility:** {state['feasibility']['overall']}. The requester approved the draft; "
        "it is waiting for Data Team review (🛡 Data Team review tab)."
    )
    thread_ref = teams.send_message(state["request_id"], "New data request", text)
    return {"thread_ref": thread_ref}
