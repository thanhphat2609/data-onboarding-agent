"""Final summary message, posted back to the request's Teams thread."""
from agent.integrations import teams
from agent.nodes.common import format_request, output_dir, rel


def summary(state: dict) -> dict:
    feas = state["feasibility"]
    outputs = dict(state.get("outputs") or {})
    recs = []
    for src in feas["sources"]:
        rec = src.get("recommendation")
        recs.append(f"- {src['source']}: {rec['kind']} `{rec['name']}`" if rec else f"- {src['source']}: cần tìm hiểu")
    text = "\n".join(
        [
            f"**{outputs.get('title', state['request_id'])}**",
            "",
            format_request(state["request"]),
            "",
            f"**Khả thi:** {feas['overall']}" + (" — data đã có sẵn trong catalog" if feas.get("data_already_available") else ""),
            *recs,
            "",
            f"**Rủi ro:** {len(feas.get('risks') or [])}",
            f"**User Story:** {outputs.get('user_story', '')}",
        ]
    )
    out = output_dir(state)
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    teams.send_message(state["request_id"], "Request đã duyệt — User Story sẵn sàng", text)
    outputs["summary"] = rel(out / "summary.md")
    return {"outputs": outputs}
