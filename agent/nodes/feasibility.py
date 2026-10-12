"""Per-source feasibility: compare the requested date range with what is obtainable, and propose how to get the data.

All logic is plain code over playbooks + catalog; the LLM takes no part in these decisions.
"""
from datetime import timedelta

from agent import config
from agent.extraction import to_date
from agent.knowledge import lookup_playbook
from agent.nodes.common import get_today, rel


def _earliest(method: dict, today):
    """Earliest date obtainable via one access method (None = no known limit)."""
    candidates = []
    if d := to_date(method.get("available_from")):
        candidates.append(d)
    if method.get("max_lookback_days"):
        candidates.append(today - timedelta(days=int(method["max_lookback_days"])))
    return max(candidates) if candidates else None


def assess_source(source: str, request: dict, models: list[dict], today) -> dict:
    start = to_date(request["date_range"]["start"])
    eta = to_date(request["eta"])
    result = {"source": source, "playbook": None, "playbook_status": None, "options": [], "recommendation": None, "gap": None, "risks": []}

    pb = lookup_playbook(source)
    if pb is None:
        result["gap"] = {
            "type": "unknown_source",
            "source": source,
            "message": f"[{source}] No playbook for this source yet — access method and date range are unknown.",
        }
        result["risks"].append(f"Source `{source}` has no playbook; the Data Team must investigate before committing.")
        return result

    ref = pb["_file"]
    result["playbook"] = ref
    result["playbook_status"] = pb.get("review_status", "draft")
    if result["playbook_status"] != "reviewed":
        result["risks"].append(f"Playbook `{ref}` has not been reviewed by the team — date range information may be inaccurate.")

    for m in models:
        if m.get("source") != source:
            continue
        data_from = to_date(m.get("data_from"))
        result["options"].append(
            {
                "kind": "existing_model",
                "name": m["name"],
                "available_from": data_from.isoformat() if data_from else None,
                "covers": data_from is None or data_from <= start,
                "lead_time_days": 1,
                "ref": rel(config.CATALOG_PATH),
            }
        )
    for method in pb.get("access_methods", []):
        earliest = _earliest(method, today)
        result["options"].append(
            {
                "kind": "ingest",
                "name": method["type"],
                "available_from": earliest.isoformat() if earliest else None,
                "covers": earliest is None or earliest <= start,
                "lead_time_days": method.get("typical_lead_time_days"),
                "notes": method.get("notes", ""),
                "connector": pb.get("current_connector"),
                "ref": ref,
            }
        )

    if not result["options"]:
        result["gap"] = {"type": "unknown_source", "source": source, "message": f"[{source}] The playbook has no access methods."}
        return result

    covering = [o for o in result["options"] if o["covers"]]
    if covering:
        result["recommendation"] = covering[0]  # existing models come first, so they are preferred
    else:
        best = min(result["options"], key=lambda o: o["available_from"])
        result["recommendation"] = best
        result["gap"] = {
            "type": "date_range",
            "source": source,
            "requested_start": start.isoformat(),
            "available_from": best["available_from"],
            "message": (
                f"[{source}] You need data from {start}, but the earliest available is {best['available_from']} "
                f"(via `{best['name']}`, per {best['ref']})."
            ),
        }

    rec = result["recommendation"]
    if rec.get("lead_time_days") and eta and today + timedelta(days=int(rec["lead_time_days"])) > eta:
        result["risks"].append(
            f"ETA {eta} is tight: `{rec['name']}` usually takes ~{rec['lead_time_days']} days (per {rec['ref']})."
        )
    return result


def feasibility(state: dict) -> dict:
    today = get_today(state)
    request = state["request"]
    accepted = set(state.get("accepted_gaps") or [])
    models = state.get("existing_models") or []

    per_source = [assess_source(s, request, models, today) for s in request.get("sources", [])]
    gaps = [
        r["gap"]
        for r in per_source
        if r["gap"] and f"{r['gap']['type']}:{r['source']}" not in accepted
    ]
    risks = [risk for r in per_source for risk in r["risks"]]
    if demo := config.demo_parts():
        risks.insert(0, f"Using DEMO {' + '.join(demo)} from `demo/` — feasibility results are illustrative only.")
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
