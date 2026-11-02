"""Per-source feasibility from the two platform repositories: is the requested data already modelled in dbt
(transformation repo), already landing in the lake (ingestion jobs), from a system that is already onboarded
(ingestion connections), or from a source type the platform can onboard (ingestion source templates)?

All logic is plain code over agent/repos.py; the LLM takes no part in these decisions.
"""
from datetime import timedelta

from agent import config, repos
from agent.workflow.extraction import to_date
from agent.repos.lookup import singular, tokenize
from agent.workflow.nodes.common import get_today

# What has to be built, from least to most work, with the team's rough estimate in days.
# Used only to flag tight ETAs; adjust to the team's real experience.
LEAD_TIME_DAYS = {"existing_model": 1, "landed": 3, "new_job": 5, "new_connection": 10}


def _repo_ref(repo: str, path: str) -> str:
    """``repo: path`` with the repo's short name, as a reference in the report."""
    return f"{repo.split('/')[-1]}: {path}"


def _requested_tables(request: dict, known: set[str]) -> set[str]:
    """Known tables of the system that the request mentions ("customers" matches "customer")."""
    words = {singular(t) for t in tokenize(f"{request.get('dataset_description', '')} {request.get('grain', '')}")}
    return {t for t in known if singular(t) in words}


# Parts of dbt model names that are not table names: layer prefixes and common suffixes.
_MODEL_NAME_NOISE = {"stg", "int", "fct", "dim", "base", "mart", "current", "daily", "latest", "history", "snapshot"}


def _model_tables(model: dict) -> set[str]:
    """Table-like words of a model name: crm_customers_current -> {"customer"} (system and layer words dropped)."""
    return {singular(t) for t in model["name"].split("_") if t and t != model.get("system") and t not in _MODEL_NAME_NOISE}


def assess_source(source: str, request: dict, models: list[dict], today, kb: repos.Knowledge) -> dict:
    """Feasibility of one requested source: an existing dbt model, an existing job, a new job or a gap, plus risks."""
    eta = to_date(request["eta"])
    system, stype = repos.parse_source(source, kb)
    result = {"source": source, "system": system, "recommendation": None, "gap": None, "risks": []}
    jobs, conns = kb.jobs_for(system), kb.connections_for(system)
    candidates = [m for m in models if m.get("system") == system]

    # Table level: "CRM segments" is not covered by a model of CRM customers.
    known_tables = {j["table"] for j in jobs} | {t for m in kb.models_for(system) for t in _model_tables(m)}
    wanted = _requested_tables(request, known_tables)
    if jobs or candidates:
        if wanted:
            jobs = [j for j in jobs if j["table"] in wanted]
            candidates = [m for m in candidates if {singular(t) for t in wanted} & _model_tables(m)]
        else:
            # Nothing the request says matches a table we know: assume it needs a table that isn't there yet.
            landed = ", ".join(sorted({j["table"] for j in kb.jobs_for(system)})) or "none"
            result["risks"].append(
                f"The request doesn't name a table of `{system}` that the platform knows (landing today: {landed}); "
                f"the Data Team should confirm which tables are needed."
            )
            jobs, candidates = [], []

    if candidates:
        best = sorted(candidates, key=lambda m: (m.get("layer") != "mart", -m.get("score", 0)))[0]
        rec = {"kind": "existing_model", "name": best["name"], "ref": _repo_ref(config.TRANSFORMATION_REPO, best["path"])}
    elif jobs:
        rec = {
            "kind": "landed",
            "name": ", ".join(j["name"] for j in jobs),
            "tables": [j["path"] for j in jobs],
            "schedule": ", ".join(sorted({str(j["schedule"]) for j in jobs})),
            "ref": _repo_ref(config.INGESTION_REPO, ", ".join(j["file"] for j in jobs)),
        }
    elif conns:
        conn = conns[0]
        rec = {"kind": "new_job", "name": conn["name"], "template": conn["template"], "ref": _repo_ref(config.INGESTION_REPO, conn["file"])}
    elif stype and stype in kb.templates:
        rec = {"kind": "new_connection", "name": stype, "ref": _repo_ref(config.INGESTION_REPO, kb.templates[stype]["file"])}
    else:
        if stype:
            why = f"`{stype}` has no source template in the ingestion repo"
        elif system in kb.systems():
            why = (f"`{system}` has dbt models but no connection in the ingestion repo; name its source type "
                   f"(e.g. \"{system} on SQL Server\") to onboard it")
        else:
            why = "it is not an onboarded system and no supported source type was named"
        result["gap"] = {
            "type": "unknown_source",
            "source": source,
            "message": f"[{source}] The platform can't onboard this source yet: {why}.",
        }
        result["risks"].append(f"Source `{source}` can't be onboarded by the platform yet; the Data Team must investigate before committing.")
        return result

    rec["lead_time_days"] = LEAD_TIME_DAYS[rec["kind"]]
    result["recommendation"] = rec
    if eta and today + timedelta(days=rec["lead_time_days"]) > eta:
        result["risks"].append(
            f"ETA {eta} is tight: {KIND_TEXT[rec['kind']]} usually takes ~{rec['lead_time_days']} days."
        )
    return result


KIND_TEXT = {
    "existing_model": "reusing a dbt model",
    "landed": "adding dbt models on landed data",
    "new_job": "adding an ingestion job and dbt models",
    "new_connection": "onboarding a connection, a job and dbt models",
}


def feasibility(state: dict) -> dict:
    """Assesses every source of the request, minus the gaps the requester accepted.
    Overall: gap, feasible_with_risks or feasible.
    """
    today = get_today(state)
    request = state["request"]
    accepted = set(state.get("accepted_gaps") or [])
    models = state.get("existing_models") or []
    kb = repos.get()

    per_source = [assess_source(s, request, models, today, kb) for s in request.get("sources", [])]
    gaps = [
        r["gap"]
        for r in per_source
        if r["gap"] and f"{r['gap']['type']}:{r['source']}" not in accepted
    ]
    risks = list(kb.errors) + [risk for r in per_source for risk in r["risks"]]
    start = to_date((request.get("date_range") or {}).get("start"))
    if start and start < today and any(r["recommendation"] and r["recommendation"]["kind"] != "existing_model" for r in per_source):
        risks.append(
            f"History: ingestion lands one snapshot per day from its first run, so data from {start} up to that run "
            "is only available as it is in the source today."
        )
    if gaps:
        overall = "gap"
    elif risks:
        overall = "feasible_with_risks"
    else:
        overall = "feasible"
    all_existing = bool(per_source) and all(
        r["recommendation"] and r["recommendation"]["kind"] == "existing_model" for r in per_source
    )
    return {
        "feasibility": {"overall": overall, "data_already_available": all_existing, "sources": per_source, "risks": risks},
        "gap": gaps,
    }
