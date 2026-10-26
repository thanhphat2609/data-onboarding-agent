"""Messages from the requester while their request waits for the Data Team (and questions while they check the draft).

The graph is paused at `approval`, so these messages don't go through it right away:
- a question ("any idea about Google Search Console data?") is answered from the two platform repos:
  what ingestion and transformation have for that source, with what exists today as examples. Nothing changes;
  the requester can reply **add** to add the source to the request.
- a change ("eta: 2026-12-01") is shown back first and applied only after the requester confirms with **yes**.
The caller (the web UI) keeps the pending confirmation and resumes the graph with an `edit` when it is confirmed.
"""
import re
from dataclasses import dataclass
from datetime import date

from agent import repos
from agent.state import REQUIRED_FIELDS
from agent.workflow.extraction import is_yes, norm, rule_extract, to_date, validate

FIELD_LABELS = {
    "dataset_description": "What",
    "sources": "Sources",
    "date_range": "Date range",
    "eta": "Go-live (ETA)",
    "refresh_frequency": "Refresh",
    "grain": "Grain",
    "consumers": "Used by",
}
_QUESTION_START = re.compile(
    r"^(?:any|what|which|who|where|when|why|how|is|are|do|does|did|can|could|would|will|should|have|has|"
    r"just one question|one question|question|tell me|gì|nào|có|liệu)\b"
)
_QUESTION_PHRASE = re.compile(r"\b(?:any idea|do you know|is there|are there|do we have|không\s*\??$|chưa\s*\??$)")
_CHANGE_VERB = re.compile(r"\b(?:change|update|set|move|replace|add|remove|thay đổi|đổi|sửa|thêm|bỏ)\b")
_ABOUT = re.compile(
    r"\b(?:about|for|on|regarding|về|cho)\s+(.+?)\s*(?:\bdata\b|dữ liệu)?\s*[?.!]*$"
    r"|(?:dữ liệu|data from|data of)\s+(?:từ\s+|của\s+)?(.+?)\s*(?:không|chưa)?\s*[?.!]*$"
)
_NO = re.compile(r"^(?:no|nope|cancel|keep|keep it|không|thôi|hủy)\b")


@dataclass
class FollowUp:
    reply: str                    # markdown for the chat
    pending: dict | None = None   # {"kind": "edit" | "add_source", "comment": str} awaiting yes/add


def is_no(text: str) -> bool:
    return bool(_NO.match(norm(text)))


def is_question(text: str) -> bool:
    t = norm(text)
    return t.endswith("?") or bool(_QUESTION_START.match(t)) or bool(_QUESTION_PHRASE.search(t))


def confirms(text: str, pending: dict) -> bool:
    """Whether the reply confirms the pending action ("yes"/"ok", or "add" for an offered source)."""
    t = norm(text)
    return is_yes(t) or (pending.get("kind") == "add_source" and t.startswith(("add", "thêm")))


def _show(field: str, value) -> str:
    if field == "sources":
        return ", ".join(value)
    if field == "date_range":
        return f"{value.get('start')} → {value.get('end')}"
    return str(value)


def _asked_source(text: str, kb: repos.Knowledge) -> str | None:
    """The source a question is about: a known system, else the words after "about"/"for"/"về"."""
    if systems := repos.find_systems(text, kb):
        return systems[0]
    if m := _ABOUT.search(norm(text)):
        name = re.sub(r"\b(?:the|our|a|an)\b", " ", m.group(1) or m.group(2))
        name = re.sub(r"\s+", " ", name).strip(" ?.!")
        return name or None
    return None


def _platform_table(kb: repos.Knowledge) -> list[str]:
    """What exists today, per system: landed tables and dbt models."""
    rows = ["| System | Landing in the lake (ingestion jobs) | dbt models (transformation) |", "|---|---|---|"]
    for system in kb.systems():
        jobs = ", ".join(f"`{j['path']}` ({j['name']}, `{j['schedule']}`)" for j in kb.jobs_for(system)) or "none yet"
        models = ", ".join(f"`{m['name']}`" for m in kb.models_for(system)) or "none yet"
        rows.append(f"| {system} | {jobs} | {models} |")
    return rows if len(rows) > 2 else ["The platform has no onboarded systems yet."]


def answer_question(text: str, values: dict, kb: repos.Knowledge, draft: bool = False) -> FollowUp:
    """draft=True: the requester is still checking the draft (nothing was sent to the Data Team yet)."""
    request = values.get("request") or {}
    rid, current = values.get("request_id", ""), ", ".join(request.get("sources", [])) or "none"
    where = "is still a draft (not sent to the Data Team yet)" if draft else "is still with the Data Team"
    footer = [
        "",
        f"Your request **{rid}** (sources: {current}) {where}, unchanged.",
    ]
    if kb.errors:
        return FollowUp("\n".join([
            "I can't check the platform right now: the ingestion/transformation repos couldn't be read "
            "(see ⚙️ Settings → Repositories).", *footer,
        ]))
    asked = _asked_source(text, kb)
    if not asked:
        return FollowUp("\n".join([
            "**What the platform has today**", "", *_platform_table(kb), *footer,
            "To ask about a specific source, name it, e.g. *\"any data about Google Search Console?\"*. "
            "To change your request, write the field and the new value, e.g. `eta: 2026-12-01`.",
        ]))

    system, stype = repos.parse_source(asked, kb)
    jobs, conns, models = kb.jobs_for(system), kb.connections_for(system), kb.models_for(system)
    templates = ", ".join(f"`{t}`" for t in kb.templates) or "none"
    lines = [f"**What the platform has for _{asked}_ today**", ""]
    if jobs:
        lines.append("- **Ingestion** (data-onboarding-ingestion): landing in the lake: "
                     + ", ".join(f"`{j['path']}` (job `{j['name']}`)" for j in jobs) + ".")
    elif conns:
        lines.append(f"- **Ingestion** (data-onboarding-ingestion): the system is onboarded (connection `{conns[0]['name']}`), "
                     "but no table of it lands in the lake yet.")
    else:
        lines.append(f"- **Ingestion** (data-onboarding-ingestion): no connection or job for it. Source types it can onboard: {templates}.")
    lines.append("- **Transformation** (data-onboarding-transformation): "
                 + (("dbt models: " + ", ".join(f"`{m['name']}`" for m in models) + ".") if models else "no dbt model for it."))

    if models:
        verdict = f"So _{asked}_ data already exists as dbt models."
    elif jobs:
        verdict = f"So raw _{asked}_ data lands in the lake, but no dbt model is built on it yet."
    elif conns:
        verdict = f"So _{asked}_ needs a new ingestion job (and dbt models) first."
    elif stype and stype in kb.templates:
        verdict = f"So _{asked}_ needs a new connection from the `{stype}` template, then a job and dbt models."
    else:
        verdict = (f"So _{asked}_ data isn't available yet, and the platform can't onboard it today "
                   "(no source template for it); the Data Team would have to investigate it first.")
    lines += ["", verdict, "", "For comparison, what exists today:", "", *_platform_table(kb)]

    if system in [repos.parse_source(s, kb)[0] for s in request.get("sources", [])]:
        return FollowUp("\n".join(lines + [*footer, f"_{asked}_ is already a source of this request."]))
    lines += [*footer, "What would you like to do?",
              f"- Reply **add** to add _{asked}_ as a source to this request (the feasibility check is re-run and the Data Team sees the change).",
              "- Click **＋ New request** to ask for it separately.",
              "- Or just wait: nothing changes."]
    return FollowUp("\n".join(lines), {"kind": "add_source", "comment": f"source: {asked}"})


def preview_change(text: str, values: dict) -> FollowUp | None:
    """The fields a message would change in the submitted request, to confirm before applying; None if none."""
    today = to_date(values.get("today")) or date.today()
    request = values.get("request") or {}
    found, _ = validate(rule_extract(text, [], today, first_message=False), today)
    changes = []
    for field in REQUIRED_FIELDS:
        if field not in found:
            continue
        new = found[field]
        if field == "sources":
            new = list(dict.fromkeys(request.get("sources", []) + new))  # edits add sources, as intake does
        if new != request.get(field):
            old = _show(field, request[field]) if request.get(field) else "—"
            changes.append(f"- **{FIELD_LABELS[field]}**: {old} → {_show(field, new)}")
    if not changes:
        return None
    return FollowUp(
        "\n".join(["Your request is with the Data Team. I'd update it like this:", "", *changes, "",
                   "Reply **yes** to apply (the feasibility check is re-run and the Data Team sees the change), "
                   "or **no** to keep it as it is."]),
        {"kind": "edit", "comment": text},
    )


def respond(text: str, values: dict, kb: repos.Knowledge | None = None) -> FollowUp:
    kb = kb or repos.get()
    change = preview_change(text, values)
    if change and (not is_question(text) or _CHANGE_VERB.search(norm(text))):
        return change
    if is_question(text) or _asked_source(text, kb):
        return answer_question(text, values, kb)
    if change:
        return change
    return FollowUp(
        "Your request is with the Data Team, unchanged. To change it, write the field and the new value, "
        "e.g. `eta: 2026-12-01` or `source: crm`. To ask about another source, e.g. *\"any data about Google Search Console?\"*."
    )
