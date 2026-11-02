"""intake node (extract + validate + compose question) and ask_user node (pause for the user's answer)."""
import re

from langgraph.types import interrupt

from agent import config, repos
from agent.workflow.extraction import is_yes, llm_extract, missing_fields, rule_extract, validate
from agent.llm.client import get_llm, load_prompt, safe_call
from agent.workflow.nodes.common import get_today
from agent.state import FIELD_QUESTIONS

STRUCTURED_FIELDS = {"sources", "date_range", "eta", "refresh_frequency"}


def extract(text: str, request: dict, asked_fields: list[str], today, first_message: bool) -> dict:
    """Request fields from a message: rules first, then the model for what the rules missed."""
    found = rule_extract(text, asked_fields, today, first_message=first_message)
    llm = get_llm()
    if llm:
        llm_found = safe_call(
            llm_extract, llm, load_prompt("intake_extract"), request, missing_fields(request), text, today, default={}
        )
        # Rules are more precise for dates/sources; the LLM is better at free-text fields.
        for field, val in llm_found.items():
            if field not in STRUCTURED_FIELDS or field not in found:
                found[field] = val
    return found


def _merge(request: dict, found: dict, text: str, incremental: bool) -> dict:
    """incremental=True (edits after review): new sources are added unless the user says 'bỏ'/'chỉ' (remove/only)."""
    request = dict(request)
    for field, val in found.items():
        if field == "sources" and incremental and request.get("sources"):
            if not re.search(r"\b(bỏ|chỉ|only|remove)\b", text.lower()):
                val = list(dict.fromkeys(request["sources"] + val))
        request[field] = val
    return request


def accept_gaps(request: dict, gaps: list[dict]) -> tuple[dict, list[str]]:
    """Applies the requester's choice to accept gaps; returns the request and the accepted gap keys."""
    request = dict(request)
    accepted = []
    new_starts = [g["available_from"] for g in gaps if g["type"] == "date_range"]
    if new_starts:
        request["date_range"] = {**request["date_range"], "start": max(new_starts)}
    for g in gaps:
        if g["type"] == "unknown_source":
            accepted.append(f"unknown_source:{g['source']}")
    return request, accepted


def gap_question(gaps: list[dict], unclear: bool) -> str:
    """The question that lists the gaps found and how to accept or change them."""
    lines = []
    if unclear:
        lines.append("Sorry, I didn't understand that answer — could you check it again?\n")
    lines.append("I checked feasibility and found the following issue(s):")
    for g in gaps:
        lines.append(f"- {g['message']}")
    options = []
    starts = [g["available_from"] for g in gaps if g["type"] == "date_range"]
    if starts:
        options.append(f"start the date range from {max(starts)}")
    if any(g["type"] == "unknown_source" for g in gaps):
        options.append(
            "continue although the platform can't onboard that source yet — the agent will look up its public docs "
            "on the web, but those findings are unverified: the source stays *Needs investigation* and the Data Team "
            "decides how to onboard it (you can paste a link to the source's API docs with your answer)"
        )
    lines.append(f"\nReply **ok** to accept: {'; '.join(options)}.")
    lines.append("Or propose an alternative, e.g. `date range: 2024-01-01 to now` or `source: ga4`.")
    return "\n".join(lines)


def new_sources(request: dict) -> list[str]:
    """Sources new to the platform: those it can't onboard yet (the gap in feasibility) and new APIs, which the
    `rest_api` template onboards but whose auth and pagination still have to be found (repos.needs_research)."""
    kb = repos.get()
    return [s for s in request.get("sources") or [] if repos.needs_research(*repos.parse_source(s, kb), kb)]


def _field_question(field: str, request: dict) -> str:
    """The question for a field; the sources question lists the systems onboarded in the ingestion repo."""
    systems = ", ".join(repos.get().systems()) or "none yet"
    names = " and ".join(f"**{s}**" for s in new_sources(request)) or "this source"
    return FIELD_QUESTIONS[field].replace("{systems}", systems).replace("{new_sources}", names)


def fields_question(fields: list[str], errors: dict, first: bool, unreadable: str = "", notes: list[str] = (),
                    request: dict | None = None) -> str:
    """unreadable: the user's last answer when nothing in it matched the questions asked."""
    lines = list(notes)
    if unreadable:
        quoted = unreadable if len(unreadable) <= 80 else unreadable[:77] + "…"
        lines.append(f"Sorry, I couldn't match “{quoted}” to my questions. Could you answer in the format below?\n")
    for field in fields:
        if field in errors:
            lines.append(f"⚠️ {errors[field]}")
    lines.append("Hi! I need a few details to set up your request:" if first else "I need a bit more information:")
    for i, field in enumerate(fields, 1):
        lines.append(f"{i}. {_field_question(field, request or {})}")
    if len(fields) > 1:
        lines.append("\n(Answer by number, e.g. `1. ...`, one item per line)")
    question = "\n".join(lines)
    llm = get_llm()
    if llm:
        question = safe_call(llm.complete, load_prompt("intake_question"), question, default=question) or question
    return question


def intake(state: dict) -> dict:
    """Reads the user's new messages and updates the request, answers to gap questions included.
    The router then asks for what is missing or moves on.
    """
    today = get_today(state)
    request = dict(state.get("request") or {})
    gaps = list(state.get("gap") or [])
    accepted = list(state.get("accepted_gaps") or [])
    asked = state.get("asked") or {}
    msgs = state.get("messages") or []
    n = state.get("n_processed", 0)
    text = "\n".join(m["content"] for m in msgs[n:] if m["role"] == "user").strip()

    unclear = False
    unreadable = ""  # the answer, when nothing in it matched the fields just asked
    notes: list[str] = []
    if text:
        kind = asked.get("kind")
        if kind == "gap" and gaps:
            asked_fields = ["date_range"] if any(g["type"] == "date_range" for g in gaps) else []
            found = extract(text, request, asked_fields, today, first_message=False)
            if found:
                # Answering a gap = choosing an alternative, so new sources replace the old ones.
                request = _merge(request, found, text, incremental=False)
                gaps = []
            elif is_yes(text):
                request, new_accepted = accept_gaps(request, gaps)
                accepted += new_accepted
                gaps = []
            else:
                unclear = True
        else:
            found = extract(text, request, asked.get("fields", []), today, first_message=(n == 0))
            request = _merge(request, found, text, incremental=(kind == "review"))
            # Say so instead of silently repeating the question. A partial answer is fine: the rest is just asked again.
            if kind == "fields" and asked.get("fields") and not found:
                unreadable = text
            # A relative date ("in two weeks") was turned into a calendar date: say which one. Checked on the
            # ETA itself, since the same answer may contain other dates (e.g. the date range).
            if found.get("eta") and found["eta"] not in text:
                notes.append(f"Noted: go-live date **{found['eta']}**.\n")

    request, errors = validate(request, today)
    missing = missing_fields(request)
    # Right after a new source is named: where it comes from (helps the Data Team and the web research).
    if "sources" not in missing and not request.get("source_origin") and new_sources(request):
        missing.insert(0, "source_origin")
    if "eta" in errors:  # the ⚠️ line explains it instead
        notes = [n for n in notes if "go-live" not in n]

    if gaps:
        asked, question = {"kind": "gap"}, gap_question(gaps, unclear)
    elif missing:
        # The origin is asked on its own, as the follow-up to "which dataset": a free-text answer then maps to it.
        fields = ["source_origin"] if missing[0] == "source_origin" else missing[: config.MAX_FIELDS_PER_QUESTION]
        asked = {"kind": "fields", "fields": fields}
        question = fields_question(fields, errors, first=(n == 0 and not request), unreadable=unreadable, notes=notes,
                                   request=request)
    else:
        asked, question = {}, ""

    return {
        "request": request,
        "gap": gaps,
        "accepted_gaps": accepted,
        "missing_fields": missing,
        "errors": errors,
        "asked": asked,
        "pending_question": question,
        "n_processed": len(msgs),
    }


def ask_user(state: dict) -> dict:
    """Asks the pending question and waits for the answer (interrupt)."""
    question = state["pending_question"]
    answer = interrupt({"type": "question", "question": question})
    return {
        "messages": [{"role": "assistant", "content": question}, {"role": "user", "content": str(answer)}],
        "intake_turns": state.get("intake_turns", 0) + 1,
    }
