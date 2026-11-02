"""The 3 User Stories drafted once the Data Team approves a request, done in order (each blocked by the one before):

  1. Spike: the dataset   (no repo)                         source, freshness and update latency, strengths, weaknesses
  2. Ingestion            (data-onboarding-ingestion)       lands the source 1:1, append-only; non-prod, then prod
  3. Transformation       (data-onboarding-transformation)  staging with a reload window, then int and mart; non-prod, then prod

Deterministic: built from the request, the feasibility result and the web research, like the main User Story. The
spike is always there, also when the platform already has the data (a change such as new columns needs one too).
"""
import re

from agent import config


def _ref(rec: dict | None) -> str:
    """`` (reference)`` of a recommendation, or nothing."""
    return f" ({rec['ref']})" if rec and rec.get("ref") else ""


def _file_name(src: dict) -> str:
    """crm, google-search-console: the system as it would appear in a file name."""
    return re.sub(r"[^a-z0-9]+", "-", (src.get("system") or src["source"]).lower()).strip("-")


def _sources(feas: dict) -> list[dict]:
    """The per-source feasibility entries of a request."""
    return feas.get("sources") or []


def _header(state: dict, n: int, kind: str, title: str, repo: str, blocked_by: str) -> list[str]:
    """The heading block shared by the three User Stories: id, repo, dependency and go-live."""
    request = state["request"]
    return [
        f"# {title}",
        "",
        f"**Request ID:** {state['request_id']} · **User Story {n} of 3** ({kind})  ",
        f"**Repo:** {repo}  ",
        f"**Blocked by:** {blocked_by}  ",
        f"**Go-live of the request:** {request.get('eta', '?')}",
        "",
    ]


def _spike(state: dict, research: dict) -> list[str]:
    """User Story 1: a spike to understand the sources before building."""
    request, feas = state["request"], state["feasibility"]
    start = (request.get("date_range") or {}).get("start", "?")
    names = ", ".join(s["source"] for s in _sources(feas))
    lines = _header(state, 1, "spike", f"[{state['request_id']}] 1/3 Spike: {names}", "none (investigation)", "nothing")
    lines += [
        "## User Story",
        f"As the **Data Team**, we need to understand {names} before building anything, so that ingestion (2/3) and "
        f"transformation (3/3) are planned on facts: how the data is reached, how fresh it is, and what it can't do.",
        "",
        "## What we know so far",
    ]
    for src in _sources(feas):
        rec = src.get("recommendation")
        lines.append(f"**{src['source']}**")
        if rec is None:
            lines.append("- The platform can't onboard it yet (no source template).")
        elif rec["kind"] == "existing_model":
            lines.append(f"- Already modelled: dbt model `{rec['name']}`{_ref(rec)}. Check it has every column the request needs.")
        elif rec["kind"] == "landed":
            lines.append(f"- Already lands in the lake: job(s) `{rec['name']}`{_ref(rec)}.")
        elif rec["kind"] == "new_job":
            lines.append(f"- System onboarded: connection `{rec['name']}`{_ref(rec)}; the table isn't ingested yet.")
        else:
            lines.append(f"- Supported source type: template `{rec['name']}`{_ref(rec)}; no connection yet.")
        if request.get("source_origin") and (rec is None or rec["name"] == "rest_api"):
            lines.append(f"- Where it comes from (requester): {request['source_origin']}")
        f = research.get(src["source"]) or {}
        for link in (f.get("links") or [])[:3]:
            lines.append(f"- Docs (unverified): [{link['title'][:80]}]({link['url']})")
        if f.get("source_notes"):
            lines.append(f"- Draft source notes to check: `{f['source_notes']}`")
        lines.append("")
    lines += [
        "## To find out",
        "- **Source:** what it is, where it comes from, access method (API, database, file export, BigQuery link…), "
        "authentication, account owner.",
        "- **Freshness:** how often the source updates, and its **update latency** (how many days data still changes, "
        "e.g. 2–3 days). It sets the staging reload window in 3/3.",
        f"- **History:** can data be pulled back to {start}? How far back does the source keep it?",
        f"- **Grain and fields:** can it give `{request.get('grain', '?')}` with every field the request needs?",
        "- **Strengths:** what it does well for this request.",
        "- **Weaknesses:** quotas and rate limits, sampling, missing fields, history limits, other risks.",
    ]
    questions = [q for f in research.values() for q in (f.get("questions") or [])]
    if questions:
        lines += ["", "## Questions from the web research"] + [f"- {q}" for q in questions]
    lines += [
        "",
        "## Acceptance Criteria",
        "- [ ] Go / no-go, with the access route the platform will use.",
        "- [ ] Update latency in days, written down for 3/3 (staging reload window).",
        f"- [ ] History confirmed from {start}, or the earliest date the source allows.",
        "- [ ] Strengths and weaknesses written in a short spike note, linked from 2/3 and 3/3.",
    ]
    if research:
        lines.append("- [ ] Draft source notes checked and corrected.")
    return lines


def _ingestion_steps(request: dict, src: dict) -> list[str]:
    """What to build in ingestion for one source, depending on its recommendation."""
    rec, system = src.get("recommendation"), _file_name(src)
    freq = request.get("refresh_frequency", "daily")
    if rec is None:
        return [
            f"Add a source template for `{src['source']}` in `code/templates/sources/` (from the spike's access route), "
            "or the route the spike decided.",
            f"Onboard a connection `pipelines/connections/{system}-<env>.yaml` from it (read-only login, secret as `env://`).",
            f"Add a job `pipelines/jobs/{system}-<table>-{freq}.yaml` on that connection.",
        ]
    if rec["kind"] in ("existing_model", "landed"):
        already = f"is already modelled in dbt (`{rec['name']}`)" if rec["kind"] == "existing_model" else f"already lands (job `{rec['name']}`)"
        return [
            f"The data {already}: no new job, unless the spike found missing columns. Then update the "
            "job's query and **re-ingest** the history the request needs.",
        ]
    if rec["kind"] == "new_job":
        return [f"Add a job `pipelines/jobs/{system}-<table>-{freq}.yaml` on connection `{rec['name']}` with the needed `SELECT`."]
    if rec["name"] == "rest_api":
        # Ingestion ADR-0015: Airflow's fetch task lands the API's records on Redpanda, Flink reads them as `landing`.
        return [
            f"Onboard a connection `pipelines/connections/{system}-<env>.yaml` from the `rest_api` source template: "
            "`base_url`, `auth`, and the token as `env://` (from the spike's notes).",
            f"Add a job `pipelines/jobs/{system}-<endpoint>-{freq}.yaml` with `endpoint`, `records_path` and "
            "`pagination` from the API docs. Its query is Flink SQL over the table `landing`; keep `payload` (the "
            "record's JSON) so a changed API field never breaks the run.",
        ]
    return [
        f"Onboard a connection `pipelines/connections/{system}-<env>.yaml` from the `{rec['name']}` source template "
        "(read-only login, secret as `env://`).",
        f"Add a job `pipelines/jobs/{system}-<table>-{freq}.yaml` on that connection.",
    ]


def _ingestion(state: dict) -> list[str]:
    """User Story 2: land the sources in the lake."""
    request, feas = state["request"], state["feasibility"]
    dr = request.get("date_range") or {}
    freq = request.get("refresh_frequency", "daily")
    names = ", ".join(s["source"] for s in _sources(feas))
    lines = _header(state, 2, "ingestion", f"[{state['request_id']}] 2/3 Ingestion: {names}",
                    f"data-onboarding-ingestion ({config.INGESTION_REPO})", "1/3 Spike")
    lines += [
        "## User Story",
        f"As the **Data Team**, we need {names} landed in the lake **1:1 and append-only**, refreshed {freq}, "
        f"from {dr.get('start', '?')}, so that transformation (3/3) can build on it.",
        "",
        "## What to build",
    ]
    for src in _sources(feas):
        lines.append(f"**{src['source']}**")
        lines += [f"{i}. {step}" for i, step in enumerate(_ingestion_steps(request, src), 1)]
        lines.append("")
    lines += [
        "Rules: land the source as it is (no business logic), append-only, one `ingest_date` per run; late changes are "
        "handled by the staging reload window in 3/3.",
        "",
        "## Non-prod",
        "- Add the files in a codespace of data-onboarding-ingestion; a new `env://` secret goes in Codespaces secrets.",
        "- Run the job by hand; the row count matches the source for a sample day.",
        "",
        "## Prod",
        "- Pull request to `pipelines/` (ADR-0014), CI green, merged: the files sync to VM 1 on their own.",
        "- A new `env://` reference: add its line to `infrastructure/prod/vm1/sources.env.example` in the same pull "
        "request, the GitHub secret of the same name, then run **Actions → Deploy** once (ADR-0013).",
        f"- Backfill from {dr.get('start', '?')}.",
        "",
        "## Acceptance Criteria",
        "- [ ] Non-prod: a run lands the data with the requested columns; row counts match the source.",
        f"- [ ] Prod: the job runs {freq} on schedule and lands data from {dr.get('start', '?')}.",
        "- [ ] Connection and job files merged to `main`; secrets only as `env://` references.",
    ]
    return lines


def _transformation(state: dict) -> list[str]:
    """User Story 3: build the dataset in dbt."""
    request, feas = state["request"], state["feasibility"]
    dr = request.get("date_range") or {}
    grain, freq = request.get("grain", "?"), request.get("refresh_frequency", "daily")
    names = ", ".join(s["source"] for s in _sources(feas))
    lines = _header(state, 3, "transformation", f"[{state['request_id']}] 3/3 Transformation: {names}",
                    f"data-onboarding-transformation ({config.TRANSFORMATION_REPO})", "2/3 Ingestion")
    lines += [
        "## User Story",
        f"As **{request.get('consumers', '?')}**, I need _{request.get('dataset_description', '')}_ at grain "
        f"**{grain}**, refreshed **{freq}**, from **{dr.get('start', '?')}**, live by **{request.get('eta', '?')}**.",
        "",
        "## What to build",
    ]
    for src in _sources(feas):
        rec, system = src.get("recommendation"), _file_name(src).replace("-", "_")
        lines.append(f"**{src['source']}**")
        if rec and rec["kind"] == "existing_model":
            lines += [
                f"1. Reuse dbt model `{rec['name']}`{_ref(rec)}; add the columns the spike found missing, if any.",
                f"2. A mart at grain `{grain}` on top of it if the grain differs.",
            ]
        else:
            lines += [
                f"1. **Staging** `stg_{system}__<table>`: a staging macro takes the landed data 1:1 and **reloads a window** "
                "of the last N days, N = the update latency from 1/3 (ingestion only appends).",
                f"2. **Int**: the transformations to grain `{grain}`.",
                "3. **Mart**: the final model with the metadata columns `_dbt_loaded_at` and `_dbt_run_date`.",
            ]
        lines.append("")
    lines += [
        "Tests: `not_null` / `unique` on keys, and a freshness test matching the refresh frequency. The int and mart "
        "detail is agreed with the Data Team.",
        "",
        "## Non-prod",
        "- `dbt build` against the non-prod target; reconcile a few days with the source UI.",
        "",
        "## Prod",
        f"- Pull request merged, models built in prod, backfill from {dr.get('start', '?')}, freshness test green.",
        "",
        "## Acceptance Criteria",
        f"- [ ] Data complete from {dr.get('start', '?')} to {dr.get('end', '?')} at grain `{grain}`.",
        f"- [ ] Refreshes {freq}; staging reloads the last N days (N from 1/3); freshness test green.",
        "- [ ] Numbers reconcile with the source UI within the tolerance agreed by the Data Team.",
        f"- [ ] Live and handed over to {request.get('consumers', '?')} by {request.get('eta', '?')}.",
    ]
    return lines


def user_stories(state: dict, research: dict) -> list[dict]:
    """[{"key", "title", "markdown"}] for the 3 User Stories, in order."""
    out = []
    for key, lines in (("spike", _spike(state, research)), ("ingestion", _ingestion(state)),
                       ("transformation", _transformation(state))):
        out.append({"key": key, "title": lines[0].removeprefix("# "), "markdown": "\n".join(lines) + "\n"})
    return out
