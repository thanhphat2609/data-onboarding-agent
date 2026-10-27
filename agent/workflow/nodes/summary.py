"""Final summary message, posted back to the request's Teams thread."""
from agent.integrations import teams
from agent.workflow.nodes.common import format_request, output_dir, rel
from agent.workflow.nodes.draft_us import current_research


def _questions(research: dict) -> list[str]:
    if not research:
        return []
    lines = ["", "**Questions for the Data Team** (sources the platform can't onboard yet; web research in the User Story, unverified):"]
    for source, f in research.items():
        lines += [f"- {source}: {q}" for q in f.get("questions") or []]
        if f.get("links"):
            lines.append(f"- {source} links: " + ", ".join(f"[{i}]({link['url']})" for i, link in enumerate(f["links"], 1)))
    return lines + [""]


def summary(state: dict) -> dict:
    feas = state["feasibility"]
    outputs = dict(state.get("outputs") or {})
    recs = []
    for src in feas["sources"]:
        rec = src.get("recommendation")
        recs.append(f"- {src['source']}: {rec['kind']} `{rec['name']}`" if rec else f"- {src['source']}: needs investigation")
    text = "\n".join(
        [
            f"**{outputs.get('title', state['request_id'])}**",
            "",
            format_request(state["request"]),
            "",
            f"**Feasibility:** {feas['overall']}" + (" — data already available in the catalog" if feas.get("data_already_available") else ""),
            *recs,
            "",
            f"**Risks:** {len(feas.get('risks') or [])}",
            *_questions(current_research(state)),
            "**User Stories** (in order):",
            *[f"{i}. {s['title']} — {s['file']}" for i, s in enumerate(outputs.get("stories") or [], 1)],
            f"**Main User Story:** {outputs.get('user_story', '')}",
        ]
    )
    out = output_dir(state)
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    teams.send_message(state["request_id"], "Request approved — User Story ready", text)
    outputs["summary"] = rel(out / "summary.md")
    return {"outputs": outputs}
