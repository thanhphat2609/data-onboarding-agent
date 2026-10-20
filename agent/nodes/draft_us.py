"""Draft the User Story + pipeline proposal. Fixed template; the LLM (if any) only writes title/description."""
import json

from agent.llm import get_llm, load_prompt, safe_call
from agent.nodes.common import output_dir, rel

KIND_LABEL = {"existing_model": "Reuse existing model", "ingest": "New ingestion"}


def current_research(state: dict) -> dict:
    """Research for the sources still in the request (a reviewer edit may have dropped one)."""
    sources = {s["source"] for s in state["feasibility"]["sources"] if s.get("recommendation") is None}
    return {k: v for k, v in (state.get("research") or {}).items() if k in sources}


def research_section(research: dict) -> list[str]:
    if not research:
        return []
    lines = [
        "## Web research (unverified)",
        "_For sources without a playbook the agent read public docs. Nothing here has been checked by the team "
        "and none of it was used in the feasibility result._",
        "",
    ]
    for source, f in research.items():
        lines.append(f"**{source}**")
        if f.get("summary"):
            lines.append(f["summary"])
        for m in f.get("access_methods") or []:
            limit = f", lookback ~{m['max_lookback_days']} days" if m.get("max_lookback_days") else ""
            lines.append(f"- Possible access: `{m['type']}`{limit} — {m.get('notes', '')} ([source]({m.get('evidence')}))")
        for p in f.get("key_passages") or []:
            lines.append(f"- {p['topic']}: “{p['text']}” ([source]({p['url']}))")
        read = [p for p in f.get("pages") or [] if not p.get("error")]
        failed = [p for p in f.get("pages") or [] if p.get("error")]
        if read:
            lines.append("- Pages read: " + ", ".join(f"[{p['title'][:60]}]({p['url']}) ({p['origin']})" for p in read))
        if failed:
            lines.append("- Could not read: " + ", ".join(f"{p['url']} ({p['error'][:80]})" for p in failed))
        lines += [f"- Note: {n}" for n in f.get("notes") or []]
        if f.get("draft_playbook"):
            lines.append(f"- Draft playbook: `{f['draft_playbook']}`")
        lines.append("")
    lines.append("## Questions for the Data Team")
    n = 0
    for source, f in research.items():
        for q in f.get("questions") or []:
            n += 1
            lines.append(f"{n}. **{source}** — {q}")
    lines.append("")
    return lines


def _pipeline_steps(request: dict, src: dict, research: dict | None = None) -> list[str]:
    source = src["source"]
    rec = src.get("recommendation")
    grain = request.get("grain", "")
    consumers = request.get("consumers", "")
    if rec is None:
        draft = (research or {}).get("draft_playbook")
        return [
            f"Data Team answers the questions below for `{source}` (no playbook yet) and picks an access method.",
            f"Review the draft playbook `{draft}` and save it to `playbooks/`." if draft else f"Write `playbooks/{source}.yaml`.",
            "Re-run the request through the agent to get a real feasibility check.",
        ]
    if rec["kind"] == "existing_model":
        return [
            f"Reuse model `{rec['name']}` (already in the catalog, data from {rec['available_from'] or 'n/a'}).",
            f"Build a mart model/view at grain `{grain}` if the existing model has a different grain.",
            f"Expose to: {consumers}.",
        ]
    connector = rec.get("connector") or "current connector"
    return [
        f"Ingest `{source}` via `{rec['name']}` ({connector}), schedule: {request.get('refresh_frequency')}.",
        f"Backfill from {request['date_range']['start']}.",
        f"Staging model `stg_{source}__*` → mart at grain `{grain}`.",
        "Add dbt tests: not_null/unique on keys, freshness matching the refresh frequency.",
        f"Expose to: {consumers}.",
    ]


def render_user_story(state: dict, title: str, description: str, extra_ac: list[str]) -> str:
    request = state["request"]
    feas = state["feasibility"]
    research = current_research(state)
    dr = request["date_range"]
    lines = [
        f"# {title}",
        "",
        f"**Request ID:** {state['request_id']}  ",
        f"**Teams thread:** {state.get('thread_ref', '')}  ",
        f"**Feasibility:** {feas['overall']}"
        + ("  \n**Data already in catalog:** yes" if feas.get("data_already_available") else ""),
        "",
        "## User Story",
        f"As **{request['consumers']}**, I need: _{request['dataset_description']}_ — "
        f"at grain **{request['grain']}**, refreshed **{request['refresh_frequency']}**, "
        f"from **{dr['start']}** to **{dr['end']}**, live by **{request['eta']}**.",
        "",
        "## Description",
        description,
        "",
        "## Sources & feasibility",
        "| Source | Proposed approach | Data available from | Covers date range | Reference |",
        "|---|---|---|---|---|",
    ]
    for src in feas["sources"]:
        rec = src.get("recommendation")
        if rec:
            lines.append(
                f"| {src['source']} | {KIND_LABEL[rec['kind']]}: `{rec['name']}` | {rec['available_from'] or 'no known limit'} "
                f"| {'✅' if rec['covers'] else '⚠️ no'} | {rec['ref']} |"
            )
        else:
            note = "no playbook — see web research below" if src["source"] in research else "no playbook"
            lines.append(f"| {src['source']} | Needs investigation | ? | ? | {note} |")

    lines += ["", "## Proposed pipeline"]
    for src in feas["sources"]:
        lines.append(f"**{src['source']}**")
        lines += [f"{i}. {step}" for i, step in enumerate(_pipeline_steps(request, src, research.get(src["source"])), 1)]
        lines.append("")

    lines += research_section(research)

    ac = [
        f"Data is complete from {dr['start']} to {dr['end']} at grain `{request['grain']}`.",
        f"Pipeline refreshes {request['refresh_frequency']}, with a matching freshness test.",
        "Numbers reconcile with the source UI within the tolerance agreed by the Data Team.",
        f"Live and handed over to {request['consumers']} by {request['eta']}.",
    ] + extra_ac
    lines += ["## Acceptance Criteria"] + [f"- [ ] {c}" for c in ac]

    risks = feas.get("risks") or []
    accepted = state.get("accepted_gaps") or []
    lines += ["", "## Risks"] + ([f"- {r}" for r in risks] or ["- No risks found."])
    if accepted:
        lines.append(f"- Accepted by the requester: {', '.join(accepted)}.")
    if state.get("review_comment"):
        lines += ["", "## Reviewer notes", state["review_comment"]]
    lines += ["", "---", "_Draft generated by the agent. Date range information comes from the playbook/catalog in the \"Reference\" column._"]
    return "\n".join(lines) + "\n"


def draft_us(state: dict) -> dict:
    request = state["request"]
    desc = request["dataset_description"]
    short = desc if len(desc) <= 80 else desc[:80].rsplit(" ", 1)[0] + "…"
    title = f"[Data Request] {short}"
    description = (
        f"Requested by {request['consumers']}: \"{desc}\". Sources: {', '.join(request['sources'])}. "
        f"Collected through the Data Onboarding Agent and approved."
    )
    extra_ac: list[str] = []
    llm = get_llm()
    if llm:
        payload = json.dumps({"request": request, "feasibility": state["feasibility"]}, ensure_ascii=False)
        gen = safe_call(llm.complete_json, load_prompt("draft_us"), payload, default={}) or {}
        title = gen.get("title") or title
        description = gen.get("description") or description
        extra_ac = [str(x) for x in (gen.get("extra_acceptance_criteria") or [])][:3]

    md = render_user_story(state, title, description, extra_ac)
    out = output_dir(state)
    (out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "feasibility.json").write_text(json.dumps(state["feasibility"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "user_story.md").write_text(md, encoding="utf-8")
    return {"outputs": {**(state.get("outputs") or {}), "title": title, "user_story": rel(out / "user_story.md")}}
