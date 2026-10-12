"""intake node (extract + validate + compose question) and ask_user node (pause for the user's answer)."""
import re

from langgraph.types import interrupt

from agent import config
from agent.extraction import is_yes, llm_extract, missing_fields, rule_extract, validate
from agent.llm import get_llm, load_prompt, safe_call
from agent.nodes.common import get_today
from agent.state import FIELD_QUESTIONS

STRUCTURED_FIELDS = {"sources", "date_range", "eta", "refresh_frequency"}


def extract(text: str, request: dict, asked_fields: list[str], today, first_message: bool) -> dict:
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
    lines = []
    if unclear:
        lines.append("Mình chưa hiểu câu trả lời, bạn xem lại giúp nhé.\n")
    lines.append("Mình đã kiểm tra khả thi và thấy vấn đề sau:")
    for g in gaps:
        lines.append(f"- {g['message']}")
    options = []
    starts = [g["available_from"] for g in gaps if g["type"] == "date_range"]
    if starts:
        options.append(f"bắt đầu date range từ {max(starts)}")
    if any(g["type"] == "unknown_source" for g in gaps):
        options.append("tiếp tục với nguồn chưa có playbook (Data Team sẽ tìm hiểu thêm)")
    lines.append(f"\nTrả lời **đồng ý** để chấp nhận: {'; '.join(options)}.")
    lines.append("Hoặc nhập phương án khác, vd. `date range: 2024-01-01 đến nay` hoặc `nguồn: ga4`.")
    return "\n".join(lines)


def fields_question(fields: list[str], errors: dict, first: bool) -> str:
    lines = []
    for field in fields:
        if field in errors:
            lines.append(f"⚠️ {errors[field]}")
    lines.append("Chào bạn! Mình cần vài thông tin để lên request:" if first else "Mình cần thêm thông tin:")
    for i, field in enumerate(fields, 1):
        lines.append(f"{i}. {FIELD_QUESTIONS[field]}")
    if len(fields) > 1:
        lines.append("\n(Trả lời theo số, vd. `1. ...` mỗi ý một dòng)")
    question = "\n".join(lines)
    llm = get_llm()
    if llm:
        question = safe_call(llm.complete, load_prompt("intake_question"), question, default=question) or question
    return question


def intake(state: dict) -> dict:
    today = get_today(state)
    request = dict(state.get("request") or {})
    gaps = list(state.get("gap") or [])
    accepted = list(state.get("accepted_gaps") or [])
    asked = state.get("asked") or {}
    msgs = state.get("messages") or []
    n = state.get("n_processed", 0)
    text = "\n".join(m["content"] for m in msgs[n:] if m["role"] == "user").strip()

    unclear = False
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

    request, errors = validate(request, today)
    missing = missing_fields(request)

    if gaps:
        asked, question = {"kind": "gap"}, gap_question(gaps, unclear)
    elif missing:
        fields = missing[: config.MAX_FIELDS_PER_QUESTION]
        asked, question = {"kind": "fields", "fields": fields}, fields_question(fields, errors, first=(n == 0 and not request))
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
    question = state["pending_question"]
    answer = interrupt({"type": "question", "question": question})
    return {
        "messages": [{"role": "assistant", "content": question}, {"role": "user", "content": str(answer)}],
        "intake_turns": state.get("intake_turns", 0) + 1,
    }
