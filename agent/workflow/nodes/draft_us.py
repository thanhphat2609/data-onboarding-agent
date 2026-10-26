"""Draft the User Story + pipeline proposal. Fixed template; the LLM (if any) only writes title/description."""
import json

from agent.llm.client import get_llm, load_prompt, safe_call
from agent.workflow.nodes.common import output_dir, rel

KIND_LABEL = {
    "existing_model": "Reuse existing dbt model",
    "landed": "Landed in the lake, add dbt models",
    "new_job": "System onboarded, add an ingestion job",
    "new_connection": "Onboard a new connection",
}


def current_research(state: dict) -> dict:
    """Research for the sources still in the request (a reviewer edit may have dropped one)."""
    sources = {s["source"] for s in state["feasibility"]["sources"] if s.get("recommendation") is None}
    return {k: v for k, v in (state.get("research") or {}).items() if k in sources}


def research_section(research: dict) -> list[str]:
    if not research:
        return []
    lines = [
        "## Web research (unverified)",
        "_For sources the platform can't onboard yet, the agent read public docs. Nothing here has been checked by the team "
        "and none of it was used in the feasibility result._",
        "",
    ]
    for source, f in research.items():
        lines.append(f"**{source}**")
        if f.get("summary"):
            lines.append(f["summary"])
        if f.get("links"):
            lines.append("- Top links (most relevant first, found for):")
            lines += [f"  {i}. [{link['title'][:80]}]({link['url']}) — {', '.join(link['found_for'])}"
                      for i, link in enumerate(f["links"], 1)]
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
        if f.get("docs_site"):
            lines.append(f"- Official docs site (guessed): `{f['docs_site']}`")
        if f.get("searches"):
            lines.append("- Searches (kept / off-topic results): " + "; ".join(
                f"round {s['round']}: `{s['query']}` ({s['results']} / {s.get('off_topic', 0)})" for s in f["searches"]
            ))
        lines += [f"- Note: {n}" for n in f.get("notes") or []]
        if f.get("source_notes"):
            lines.append(f"- Draft source notes: `{f['source_notes']}`")
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
    """Steps across the two repos, from what already exists to what has to be built."""
    rec = src.get("recommendation")
    system, grain, consumers = src.get("system") or src["source"], request.get("grain", ""), request.get("consumers", "")
    freq = request.get("refresh_frequency", "daily")
    dbt_steps = [
        f"data-onboarding-transformation: staging model `stg_{system}__<table>` (typed, one row per key per ingest day) "
        f"and a mart at grain `{grain}`, written as Parquet to the curated zone.",
        "Add dbt tests: not_null/unique on keys, freshness matching the refresh frequency.",
        f"Expose to: {consumers}.",
    ]
    if rec is None:
        notes = (research or {}).get("source_notes")
        return [
            f"Data Team answers the questions below for `{src['source']}` and decides how to onboard it "
            "(a new source template in data-onboarding-ingestion, or another route).",
            f"Review the draft notes `{notes}`." if notes else "Collect the source's API/export documentation.",
            "Re-run the request through the agent once the source can be onboarded.",
        ]
    if rec["kind"] == "existing_model":
        return [
            f"Reuse dbt model `{rec['name']}` ({rec['ref']}).",
            f"Build a mart at grain `{grain}` on top of it if the grain differs.",
            f"Expose to: {consumers}.",
        ]
    if rec["kind"] == "landed":
        tables = ", ".join(f"`{t}`" for t in rec.get("tables", []))
        return [f"Raw data already lands in the lake: {tables} (jobs `{rec['name']}`, schedule `{rec.get('schedule')}`)."] + dbt_steps
    if rec["kind"] == "new_job":
        return [
            f"data-onboarding-ingestion: add a job `pipelines/jobs/{system}-<table>-{freq}.yaml` on connection "
            f"`{rec['name']}` with the needed `SELECT`, scheduled {freq}.",
        ] + dbt_steps
    return [
        f"data-onboarding-ingestion: onboard a connection `pipelines/connections/{system}-{rec['name']}-<env>.yaml` "
        f"from the `{rec['name']}` source template (read-only login, secret as env:// or kv://).",
        f"Add a job `pipelines/jobs/{system}-<table>-{freq}.yaml` on that connection.",
    ] + dbt_steps


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
        + ("  \n**Data already modelled in dbt:** yes" if feas.get("data_already_available") else ""),
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
        "| Source | Proposed approach | Reference |",
        "|---|---|---|",
    ]
    for src in feas["sources"]:
        rec = src.get("recommendation")
        if rec:
            lines.append(f"| {src['source']} | {KIND_LABEL[rec['kind']]}: `{rec['name']}` | {rec['ref']} |")
        else:
            note = "can't be onboarded yet — see web research below" if src["source"] in research else "can't be onboarded yet"
            lines.append(f"| {src['source']} | Needs investigation | {note} |")
    if request.get("source_origin"):
        lines += ["", f"**Where the new source comes from (requester's words):** {request['source_origin']}"]

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
    lines += ["", "---", "_Draft generated by the agent. Facts come from data-onboarding-ingestion and data-onboarding-transformation, see the \"Reference\" column._"]
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
