"""Research sources new to the platform: ones it can't onboard yet, and new APIs (rest_api template), whose auth and
pagination still have to be found (web docs → draft source notes + questions for the Data Team).

Runs after feasibility, before approval, so the reviewer sees the findings. Each source is researched
once per request. Findings are unverified and never change the feasibility result.
"""
from agent import repos
from agent.workflow.nodes.common import output_dir, rel
from agent.research.investigate import draft_source_notes, investigate, slug


def investigate_source(state: dict) -> dict:
    """Researches the public docs of each source the platform can't onboard yet, once per source,
    and writes source_notes_<source>.yaml.
    """
    research = dict(state.get("research") or {})
    kb = repos.get()
    todo = [
        s["source"]
        for s in state["feasibility"]["sources"]
        if repos.needs_research(*repos.parse_source(s["source"], kb), kb) and s["source"] not in research
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
