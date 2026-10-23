"""Research sources the platform can't onboard yet (web docs → draft source notes + questions for the Data Team).

Runs after feasibility, before approval, so the reviewer sees the findings. Each source is researched
once per request. Findings are unverified and never change the feasibility result.
"""
from agent.nodes.common import output_dir, rel
from agent.research import draft_source_notes, investigate, slug


def investigate_source(state: dict) -> dict:
    research = dict(state.get("research") or {})
    todo = [
        s["source"]
        for s in state["feasibility"]["sources"]
        if s.get("recommendation") is None and s["source"] not in research
    ]
    if not todo:
        return {}
    out = output_dir(state)
    for source in todo:
        findings = investigate(source, state["request"], state.get("messages") or [])
        path = out / f"source_notes_{slug(source)}.yaml"
        path.write_text(draft_source_notes(source, findings), encoding="utf-8")
        findings["source_notes"] = rel(path)
        research[source] = findings
    return {"research": research}
