"""Draft the User Story + pipeline proposal. Fixed template; the LLM (if any) only writes title/description."""
import json
import zipfile

from agent.llm.client import get_llm, load_prompt, safe_call
from agent.workflow.nodes.common import output_dir, rel
from agent.workflow.stories import user_stories

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
    """Markdown lines of the unverified web research for sources the platform can't onboard yet; none without research."""
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
                f"round {s['round']}: `{s['query']}` ({s['results']} / {s.get('off_topic', 0)}{', cached' if s.get('cached') else ''})"
                for s in f["searches"]
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
    """Markdown of the parent User Story: the request, the feasibility per source and the research."""
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


def default_title(request: dict) -> str:
    """A User Story title from the dataset description, cut at 80 characters."""
    desc = request["dataset_description"]
    short = desc if len(desc) <= 80 else desc[:80].rsplit(" ", 1)[0] + "…"
    return f"[Data Request] {short}"


def default_description(request: dict, approved: bool) -> str:
    """A description from the request fields, used when no model writes one."""
    return (
        f"Requested by {request['consumers']}: \"{request['dataset_description']}\". Sources: {', '.join(request['sources'])}. "
        f"Collected through the Data Onboarding Agent" + (" and approved." if approved else ".")
    )


# Sections the requester owns, shown first in the draft; the others are folded under "Technical details".
REQUESTER_SECTIONS = ("User Story", "Acceptance Criteria", "Description")


def draft_preview(state: dict) -> dict:
    """The User Story as the requester checks it before it goes to the Data Team: same template as the final
    one, no LLM (fast; the LLM wording is added after the Data Team approves). Split into the parts the
    requester owns ("main") and the technical sections ("technical")."""
    request = state["request"]
    md = render_user_story(state, default_title(request), default_description(request, approved=False), [])
    head, *sections = md.split("\n## ")
    head = "\n".join(line for line in head.split("\n") if not line.startswith("**Teams thread:**"))  # no thread yet
    main, technical = [head.rstrip()], []
    for name in REQUESTER_SECTIONS:
        main += [f"## {sec.rstrip()}" for sec in sections if sec.split("\n", 1)[0].strip() == name]
    technical += [f"## {sec.rstrip()}" for sec in sections if sec.split("\n", 1)[0].strip() not in REQUESTER_SECTIONS]
    return {"main": "\n\n".join(main) + "\n", "technical": "\n\n".join(technical) + "\n"}


def draft_us(state: dict) -> dict:
    """Writes the User Stories, the parent user_story.md, request.json, feasibility.json and a zip
    into the request's output folder.
    """
    request = state["request"]
    title = default_title(request)
    description = default_description(request, approved=True)
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
    # The work itself: 3 User Stories, one file each, the only copy of each (to maintain and copy into the backlog).
    # user_story.md is their parent: the request, feasibility and research, with a list of the 3.
    stories = user_stories(state, current_research(state))
    files = []
    for i, story in enumerate(stories, 1):
        path = out / f"us_{i}_{story['key']}.md"
        path.write_text(story["markdown"], encoding="utf-8")
        files.append(path)
    footer = md.rfind("\n---\n")  # the list goes before the closing note
    md = md[:footer] + stories_list(stories, [f.name for f in files]) + md[footer:]
    (out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "feasibility.json").write_text(json.dumps(state["feasibility"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "user_story.md").write_text(md, encoding="utf-8")
    bundle = out / f"user_stories_{state['request_id']}.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in [out / "user_story.md", *files]:
            zf.write(f, arcname=f"{state['request_id']}/{f.name}")
    return {"outputs": {**(state.get("outputs") or {}), "title": title, "user_story": rel(out / "user_story.md"),
                        "bundle": rel(bundle),
                        "stories": [{"title": s["title"], "file": rel(f)} for s, f in zip(stories, files)]}}


def stories_list(stories: list[dict], names: list[str]) -> str:
    """The parent's list of its 3 User Stories, linked to their files (next to user_story.md, and in the zip)."""
    lines = ["", "## The 3 User Stories", "Done in order, each blocked by the one before. One file each:", ""]
    lines += [f"{i}. [{s['title']}]({name})" for i, (s, name) in enumerate(zip(stories, names), 1)]
    return "\n".join(lines) + "\n"
