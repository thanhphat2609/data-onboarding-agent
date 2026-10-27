"""Event handlers of the web UI (chat, Data Team review, sessions, settings) and the AgentRunner they share."""
import json
import time
from pathlib import Path

import gradio as gr
from langgraph.types import Command

from agent import auth, config, repos
from agent.llm import client as llm
from agent.ui.views import (
    NODE_STEP,
    _approval_html,
    _esc,
    _header_html,
    _pill,
    _request_html,
    _stage,
    _stepper_html,
)
from agent.workflow import followup
from agent.workflow.runner import AgentRunner

runner = AgentRunner()


# ---------- accounts ----------

def _user(request: gr.Request | None) -> str:
    """Login of the person behind this event ("" when the app has no login)."""
    return ((request.username if request else None) or "").strip().lower()


def _require_data_team(request: gr.Request):
    """Tabs are hidden from requesters, but handlers check too: hidden components can still be called."""
    if not auth.is_data_team(_user(request)):
        raise gr.Error("Only the Data Team can do this.")


def _owns(thread_id: str, request: gr.Request) -> bool:
    """Data Team: every session. Requester: sessions they requested, or typed themselves."""
    user = _user(request)
    if auth.is_data_team(user):
        return True
    row = runner.sessions.get(thread_id) or {}
    return user in (row.get("requested_by"), row.get("created_by"))


def _on_behalf_of(value: str, user: str) -> str:
    """Requester a Data Team member files a new request for; "" = the request is their own."""
    value = (value or "").strip().lower()
    if not value or value == user or not auth.is_data_team(user):
        return ""
    if auth.enabled() and not auth.known(value, runner.sessions):
        gr.Warning(f"{value} hasn't signed in yet: they'll see this session after their first sign-in.")
    return value


# ---------- chat ----------

WELCOME = """## 👋 What data do you need?
Describe it in your own words, in English or Vietnamese. The agent asks for anything missing
(source, date range, go-live date, refresh, grain, who uses it), checks feasibility,
and drafts a User Story: you check the draft, then the Data Team approves it.

Not sure how to start? Try one of these:"""

EXAMPLES = [
    {
        "display_text": "📇 Current CRM customers for a dashboard",
        "text": "The sales team needs the current list of CRM customers with their segment for a weekly dashboard.",
    },
    {
        "display_text": "🏷️ CRM segments (not ingested yet)",
        "text": "We need the CRM segments table (segment id and name) for the sales report.",
    },
    {
        "display_text": "🗄️ HR employees on SQL Server (new system)",
        "text": "dataset: HR employees with department and hire date\nsource: HR on SQL Server",
    },
]

PLACEHOLDERS = {
    "describe": "Describe the data you need…   (Shift+Enter for a new line)",
    "details": "Answer here, one item per line, e.g. 1. from 2024-01-01 to now   (Shift+Enter for a new line)",
    "feasibility": "Reply ok to accept, or suggest an alternative…",
    "draft": "Check the draft: click ✓ Approve draft, or type what should change, e.g. eta: 2026-12-01…",
    "review": "Waiting for the Data Team. Ask a question, or type a change (you confirm it before it's applied)…",
    "complete": "Describe another data request to start a new one…",
}

# What the "thinking" bubble says while each node runs.
NODE_STATUS = {
    "intake": "Reading your message…",
    "requester_review": "Preparing the draft…",
    "notify": "Sending your request to the Data Team…",
    "catalog_check": "Searching the dbt models…",
    "feasibility": "Checking feasibility…",
    "investigate_source": "Researching the web docs of sources the platform can't onboard yet (a few rounds, up to ~3 min)…",
    "draft_us": "Drafting the User Story…",
    "summary": "Sending the summary…",
}


def _thought(steps: list[str], running: bool, title: str) -> dict:
    """Collapsible "thought" message (Gradio metadata): spinner while pending, step list inside."""
    lines = [f"✓ {s.rstrip('…')}" for s in steps[:-1]] if running else [f"✓ {s.rstrip('…')}" for s in steps]
    if running and steps:
        lines.append(f"… {steps[-1]}")
    return {
        "role": "assistant",
        "content": "\n".join(lines) or "…",
        "metadata": {"title": title, "status": "pending" if running else "done"},
    }


def _reply(ev: dict, values: dict) -> list[dict]:
    """The assistant's chat message for an agent event."""
    if ev["type"] == "question":
        text = ev["question"]
    elif ev["type"] == "draft":
        text = (
            "I have everything I need and the feasibility check is done. **Here is the draft** (on the right): "
            "check the User Story and the acceptance criteria.\n\n"
            "- Click **✓ Approve draft** to send it to the Data Team.\n"
            "- Or type what should change (e.g. `eta: 2026-12-01`, `grain: date x page`); you get a new draft.\n\n"
            "Nothing is sent to the Data Team until you approve."
        )
    elif ev["type"] == "approval":
        text = (
            "Thanks! Your request is now with the **Data Team** for review. This page updates when they approve it "
            "or ask for changes; you can also come back later from **Sessions**."
        )
    elif ev["type"] == "done":
        title = (values.get("outputs") or {}).get("title") or values.get("request_id", "")
        text = (f"✅ Done! **{title}**\n\nUser Story created, with the 3 User Stories to do in order (spike, ingestion, "
                "transformation), and the summary was sent to the Data Team. Preview or download it on the right.")
    else:
        return []
    return [{"role": "assistant", "content": text}]


def _result(values: dict) -> tuple:
    """Title, preview and download buttons for a finished request."""
    outputs = values.get("outputs") or {}

    def path(key: str) -> str | None:
        p = config.ROOT / outputs[key] if outputs.get(key) else None
        return str(p) if p and p.exists() else None

    us, summary = path("user_story"), path("summary")
    # The download: a zip with user_story.md and the 3 User Story files (older requests: user_story.md alone).
    download = path("bundle") or us
    title = f"### ✅ {_esc(outputs.get('title') or values.get('request_id', ''))}\nUser Story and the 3 User Stories (spike, ingestion, transformation) created; the summary was sent to the Data Team."
    # The preview shows them together; each story is still its own file.
    parts = [Path(us).read_text(encoding="utf-8")] if us else []
    for story in outputs.get("stories") or []:
        if (p := config.ROOT / story["file"]).exists():
            parts.append(p.read_text(encoding="utf-8"))
    preview = "\n\n---\n\n".join(parts)
    return title, preview, gr.update(value=download, visible=bool(download)), gr.update(value=summary, visible=bool(summary))


# Outputs of every chat handler, in this order:
# thread_state, chat, box, stepper, request_card, waiting_box, waiting_html, draft_box, draft_main, draft_technical,
# result_box, result_title, result_preview, us_download, summary_download, state_json, mark, poll_timer
N_OUT = 18
SKIP = tuple(gr.update() for _ in range(N_OUT))


def _mark(ev: dict, values: dict) -> str:
    """Fingerprint of a thread's progress; the review poll compares it to spot a Data Team decision."""
    return f"{len(values.get('messages') or [])}:{ev['type']}"


def _view(thread_id: str, history: list, ev: dict | None = None) -> tuple:
    """Every panel of the Request tab, from the thread's current state."""
    values = runner.state(thread_id) if thread_id else {}
    ev = ev or (runner.current_event(thread_id) if thread_id else {"type": "empty"})
    stage = _stage(ev, values)
    review, draft, done = stage == "review", stage == "draft", stage == "complete"
    result = _result(values) if done else ("", "", gr.update(value=None, visible=False), gr.update(value=None, visible=False))
    snapshot = {k: values.get(k) for k in ("request_id", "request", "missing_fields", "gap", "existing_models", "outputs") if values.get(k)}
    waiting = _approval_html(
        ev, "Waiting for Data Team review", "The Data Team approves it or asks for changes. This page updates on its own."
    ) if review else ""
    return (
        thread_id,
        history,
        gr.update(value="", placeholder=PLACEHOLDERS[stage]),
        _stepper_html(stage),
        _request_html(values),
        gr.update(visible=review),
        waiting,
        gr.update(visible=draft),
        ev["draft"]["main"] if draft else "",
        ev["draft"]["technical"] if draft else "",
        gr.update(visible=done),
        *result,
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        _mark(ev, values),
        gr.Timer(active=review),  # poll for the Data Team's decision only while it is pending
    )


def _busy(thread_id: str, history: list, stepper=None) -> tuple:
    """While the agent runs: show the thinking bubble, clear the input, hide the waiting and draft panels."""
    keep, hide = gr.update(), gr.update(visible=False)
    return (thread_id, history, gr.update(value=""), stepper or keep, keep, hide, keep, hide, keep, keep, *[keep] * 8)


def _run(thread_id: str, graph_input, history: list):
    """Stream the graph: show the user's message and a live "thinking" block, then the real answer."""
    started, steps = time.perf_counter(), []
    yield _busy(thread_id, history + [_thought(steps, True, "Thinking…")])
    ev = {"type": "empty"}
    for ev in runner.stream(thread_id, graph_input):
        if ev["type"] == "progress" and ev["node"] in NODE_STATUS:
            steps.append(NODE_STATUS[ev["node"]])
            stepper = _stepper_html(NODE_STEP[ev["node"]])
            yield _busy(thread_id, history + [_thought(steps, True, steps[-1])], stepper)
    # Collapse into a "Thought for Xs" line above the answer, like chat assistants do.
    done = _thought(steps, False, f"Thought for {time.perf_counter() - started:.1f}s")
    yield _view(thread_id, history + [done] + _reply(ev, runner.state(thread_id)), ev)


def on_send(message: str, thread_id: str, history: list, on_behalf: str, request: gr.Request):
    message = (message or "").strip()
    if not message:
        yield SKIP
        return
    history = history + [{"role": "user", "content": message}]
    ev = runner.current_event(thread_id) if thread_id else {"type": "empty"}
    if ev["type"] == "question":
        graph_input = Command(resume=message)
    elif ev["type"] == "draft":  # checking the draft: a question is answered, anything else is a change (or "ok")
        yield from _draft_message(message, thread_id, history)
        return
    elif ev["type"] == "approval":  # waiting for the Data Team: answer questions, confirm changes first
        yield from _followup(message, thread_id, history)
        return
    else:
        user = _user(request)
        thread_id, graph_input = runner.new_request(message, user=user, on_behalf_of=_on_behalf_of(on_behalf, user))
    yield from _run(thread_id, graph_input, history)


# Follow-up actions waiting for the requester's "yes"/"add", per thread (short-lived, so kept in memory).
_PENDING: dict[str, dict] = {}


def _followup(message: str, thread_id: str, history: list):
    """A message while the request waits for review (agent/workflow/followup.py): nothing changes until confirmed."""
    pending = _PENDING.pop(thread_id, None)
    if pending and followup.confirms(message, pending):
        yield from _run(thread_id, Command(resume={"action": "edit", "comment": pending["comment"]}), history)
        return
    if pending and followup.is_no(message):
        reply = "OK, nothing changed. Your request is still with the Data Team."
    else:
        result = followup.respond(message, runner.state(thread_id))
        reply = result.reply
        if result.pending:
            _PENDING[thread_id] = result.pending
    yield _view(thread_id, history + [{"role": "assistant", "content": reply}])


def _draft_message(message: str, thread_id: str, history: list):
    """A message while the requester checks the draft. Nothing has been sent yet, so a change is applied at once
    (a new draft follows); a question is answered from the platform repos; "ok"/"approve" approves the draft."""
    pending = _PENDING.pop(thread_id, None)
    if pending and followup.confirms(message, pending):
        yield from _run(thread_id, Command(resume={"action": "edit", "comment": pending["comment"]}), history)
        return
    if followup.is_no(message):
        yield _view(thread_id, history + [{"role": "assistant", "content": "OK, the draft is unchanged. Approve it, or type what should change."}])
        return
    values = runner.state(thread_id)
    if followup.is_question(message) and not followup.preview_change(message, values):
        result = followup.answer_question(message, values, repos.get(), draft=True)
        if result.pending:
            _PENDING[thread_id] = result.pending
        yield _view(thread_id, history + [{"role": "assistant", "content": result.reply}])
        return
    yield from _run(thread_id, Command(resume=message), history)


def on_approve_draft(thread_id: str, history: list, request: gr.Request):
    """✓ Approve draft: the request goes to the Data Team."""
    if not thread_id or runner.current_event(thread_id)["type"] != "draft" or not _owns(thread_id, request):
        yield SKIP
        return
    _PENDING.pop(thread_id, None)
    history = history + [{"role": "user", "content": "✓ Approve draft"}]
    yield from _run(thread_id, Command(resume={"action": "approve"}), history)


def on_example(evt: gr.SelectData, thread_id: str, history: list, on_behalf: str, request: gr.Request):
    text = evt.value.get("text", "") if isinstance(evt.value, dict) else str(evt.value)
    yield from on_send(text, thread_id, history, on_behalf, request)


def on_poll(thread_id: str, history: list, mark: str):
    """Requester side, while waiting for review: show the Data Team's decision once it lands."""
    if not thread_id:
        return SKIP
    ev = runner.current_event(thread_id)
    values = runner.state(thread_id)
    # "empty" = the graph is still running after the decision (e.g. drafting the User Story); wait for the result.
    if ev["type"] == "empty" or _mark(ev, values) == mark:
        return SKIP
    if values.get("approved"):
        note = "✅ The **Data Team approved** your request."
    else:
        comment = values.get("review_comment") or ""
        note = f"✏️ The **Data Team updated** your request: “{comment}”. The feasibility check was re-run; please check the new draft."
    return _view(thread_id, history + [{"role": "assistant", "content": note}] + _reply(ev, values), ev)


# ---------- Data Team review ----------

def _review_queue() -> list[tuple[str, str]]:
    """Requests waiting for approval, newest first."""
    return [
        (f"{s['request_id'] or s['thread_id']} · {s['sources']} · {s['description'][:70]} · {s['requested_by'] or '-'}", s["thread_id"])
        for s in runner.sessions.recent(status="approval", limit=100)
    ]


def on_review_refresh(request: gr.Request):
    _require_data_team(request)
    choices = _review_queue()
    msg = f"**{len(choices)}** request(s) waiting for review." if choices else "Nothing waiting for review. 🎉"
    return gr.update(choices=choices, value=None), msg, gr.update(visible=False)


def on_review_open(thread_id: str, request: gr.Request):
    _require_data_team(request)
    if not thread_id:
        return gr.update(visible=False), "", "", ""
    ev = runner.current_event(thread_id)
    if ev["type"] != "approval":
        gr.Warning("This request is no longer waiting for review. Refresh the list.")
        return gr.update(visible=False), "", "", ""
    values = runner.state(thread_id)
    return gr.update(visible=True), _request_html(values), _approval_html(ev, "Feasibility check"), ""


def on_review_decision(action: str):
    def handler(thread_id: str, comment: str, request: gr.Request):
        _require_data_team(request)
        comment = (comment or "").strip()
        keep = gr.update()
        if not thread_id or runner.current_event(thread_id)["type"] != "approval":
            gr.Warning("This request is no longer waiting for review. Refresh the list.")
            return keep, keep, keep, keep, keep
        if action == "edit" and not comment:
            gr.Warning("Write what should change in the comment box first.")
            return keep, keep, keep, keep, keep
        runner.reply(thread_id, {"action": action, "comment": comment}, reviewer=_user(request) or "data team")
        values = runner.state(thread_id)
        if action == "approve":
            title = (values.get("outputs") or {}).get("title") or values.get("request_id", "")
            msg = f"✅ Approved **{values.get('request_id', '')}**. User Story created: {title}. The requester sees it in their session."
            us = _result(values)[2]
        else:
            status = SESSION_STATUS.get(runner.current_event(thread_id)["type"], "")
            msg = f"✏️ Sent back to **{values.get('request_id', '')}** with your comment. The request was updated and is now {status}."
            us = gr.update(value=None, visible=False)
        queue = _review_queue()
        return msg, us, gr.update(visible=False), gr.update(choices=queue, value=None), ""

    return handler


# ---------- sessions ----------

SESSION_STATUS = {"question": "waiting for the requester's answer", "draft": "waiting for the requester to approve the draft",
                  "approval": "waiting for Data Team review", "done": "done", "empty": "started"}


def _session_choices(user: str) -> list[tuple[str, str]]:
    """Recent sessions: all of them for the Data Team, a requester's own otherwise."""
    everyone = auth.is_data_team(user)
    choices = []
    for s in runner.sessions.recent(user=None if everyone else user, limit=30):
        label = f"{s['request_id'] or s['thread_id']} · {s['sources'] or 'no source yet'} · {SESSION_STATUS.get(s['status'], '')}"
        if everyone and s["requested_by"]:
            label += f" · {s['requested_by']}"
            if s["created_by"] and s["created_by"] != s["requested_by"]:
                label += f" (filed by {s['created_by']})"
        choices.append((label, s["thread_id"]))
    return choices


def on_refresh_sessions(request: gr.Request):
    return gr.update(choices=_session_choices(_user(request)), value=None)


def on_resume(picked: str, pasted: str, request: gr.Request):
    thread_id = (pasted or "").strip() or (picked or "")
    values = runner.state(thread_id) if thread_id else {}
    if not values or not _owns(thread_id, request):  # someone else's session looks the same as a missing one
        gr.Warning("Session not found. Pick one from the list or check the thread_id.")
        return (*SKIP, gr.update())
    history = [{"role": m["role"], "content": m["content"]} for m in values.get("messages", [])]
    return (*_view(thread_id, history), gr.Tabs(selected="request"))


# ---------- LLM settings ----------

def on_refresh_models(host: str, api_key: str, current: str, request: gr.Request):
    _require_data_team(request)
    try:
        models = llm.list_models(host, api_key)
    except Exception as exc:  # noqa: BLE001
        if "401" in str(exc):
            return gr.update(), "❌ Wrong API key."
        return gr.update(), f"❌ Cannot reach Ollama at `{host}`: {exc}"
    if not models:
        return gr.update(choices=[]), "⚠️ Ollama is running but has no models. Run `ollama pull qwen2.5:7b` first."
    value = current if current in models else models[0]
    return gr.update(choices=models, value=value), f"Found {len(models)} model(s) on `{host}`."


def on_test(host: str, api_key: str, model: str, request: gr.Request):
    _require_data_team(request)
    if not model:
        return "Pick a model before testing."
    try:
        reply, secs = llm.ping(host, model, api_key)
    except Exception as exc:  # noqa: BLE001
        return f"❌ Error: {exc}"
    return f"✅ `{model}` replied in {secs:.1f}s: {reply}"


def on_apply(host: str, api_key: str, model: str, request: gr.Request):
    _require_data_team(request)
    llm.configure(host, model, api_key)
    return f"**In use:** {llm.status()}", _header_html()


def on_disable(host: str, request: gr.Request):
    _require_data_team(request)
    llm.configure(host, "")
    return f"**In use:** {llm.status()}", _header_html()


# ---------- repositories ----------

def _repos_md() -> str:
    kb = repos.get()
    lines = [
        f"**data-onboarding-ingestion**: `{kb.origin.get('ingestion', 'not read')}`  ",
        f"{len(kb.templates)} source template(s) ({', '.join(kb.templates) or 'none'}), "
        f"{len(kb.connections)} connection(s), {len(kb.jobs)} job(s). Systems: {', '.join(kb.systems()) or 'none'}.",
        "",
        f"**data-onboarding-transformation**: `{kb.origin.get('transformation', 'not read')}`  ",
        f"{len(kb.models)} dbt model(s): {', '.join(m['name'] for m in kb.models) or 'none'}.",
    ]
    lines += [f"\n❌ {e}" for e in kb.errors]
    return "\n".join(lines)


def on_reload_repos(request: gr.Request):
    _require_data_team(request)
    repos.reload()
    return _repos_md(), _header_html()


# ---------- page load ----------

def on_load(request: gr.Request):
    """Who is signed in decides the tabs: requesters get Request + Sessions, the Data Team everything."""
    user = _user(request)
    full = auth.is_data_team(user)
    account = ""
    if user:
        role = "Data Team" if full else "Requester"
        account = (f'<div class="account">Signed in as <b>{_esc(user)}</b> {_pill(role, "blue" if full else "neutral")}'
                   ' <a href="logout">Log out</a></div>')
    return (account, *(gr.Tab(visible=full) for _ in range(3)), gr.update(choices=_session_choices(user), value=None),
            gr.update(visible=full))
