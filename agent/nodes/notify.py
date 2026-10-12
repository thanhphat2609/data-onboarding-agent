"""Notify the Data Team about a new request (sent once per request)."""
import json

from agent.integrations import teams
from agent.nodes.common import format_request, output_dir


def notify(state: dict) -> dict:
    if state.get("thread_ref"):
        return {}
    request = state["request"]
    out = output_dir(state)
    (out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    text = format_request(request) + "\n\nThe agent is checking the catalog and feasibility, and will update this thread."
    thread_ref = teams.send_message(state["request_id"], "New data request", text)
    return {"thread_ref": thread_ref}
