"""Research sources that have no playbook (web docs → draft playbook + questions for the Data Team).

Runs after feasibility, before approval, so the reviewer sees the findings. Each source is researched
once per request. Findings are unverified and never change the feasibility result.
"""
from agent.nodes.common import output_dir, rel
from agent.research import draft_playbook, investigate, slug


def investigate_source(state: dict) -> dict:
    research = dict(state.get("research") or {})
    todo = [
        s["source"]
        for s in state["feasibility"]["sources"]
        if s.get("playbook") is None and s["source"] not in research
    ]
    if not todo:
        return {}
    out = output_dir(state)
    for source in todo:
        findings = investigate(source, state["request"], state.get("messages") or [])
        path = out / f"playbook_draft_{slug(source)}.yaml"
        path.write_text(draft_playbook(source, findings), encoding="utf-8")
        findings["draft_playbook"] = rel(path)
        research[source] = findings
    return {"research": research}
