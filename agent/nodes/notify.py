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
    text = format_request(request) + "\n\nAgent đang kiểm tra catalog và khả thi, sẽ cập nhật trong thread này."
    thread_ref = teams.send_message(state["request_id"], "Data request mới", text)
    return {"thread_ref": thread_ref}
