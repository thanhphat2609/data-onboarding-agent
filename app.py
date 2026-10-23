"""Gradio web UI for the Data Onboarding Agent.

    python app.py            # local: http://127.0.0.1:7860
    python app.py --share    # temporary public link (Colab / team demo)
    python app.py --host 0.0.0.0   # GitHub Codespaces / containers, see infrastructure/README.md

Tabs:
- Request: chat + a step tracker, a live "Your request" card, the review panel (Approve / Request changes)
  and the finished User Story with download buttons. One chat session = one thread_id.
- Sessions: reopen a recent session (e.g. after a Colab disconnect) from the list or by thread_id.
- Settings: switch the Ollama host/model/API key at runtime (empty model = rule-based), e.g. a model hosted on
  Colab behind scripts/ollama_auth_proxy.py; see what was read from the ingestion and transformation repos, and reload them.
- Debug: raw agent state.
"""
import argparse
import hmac
import html
import json
import re
import time
from pathlib import Path

import gradio as gr
from langgraph.types import Command

from agent import config, llm, repos
from agent.runner import AgentRunner
from agent.state import REQUIRED_FIELDS

runner = AgentRunner()


# ---------- HTML helpers ----------

def _esc(text) -> str:
    return html.escape(str(text or ""))


def _inline(text: str) -> str:
    """Escape, then render the `code` and **bold** used in the agent's messages."""
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", _esc(text))
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


def _pill(text: str, tone: str = "neutral") -> str:
    return f'<span class="pill pill-{tone}">{_esc(text)}</span>'


def _header_html() -> str:
    model = llm.get_llm()
    model_pill = _pill(f"● {model.model}", "green") if model else _pill("○ Rule-based (no LLM)")
    kb = repos.get()
    if kb.errors:
        knowledge = _pill("Repos not readable, see Settings", "red")
    else:
        knowledge = _pill(f"{len(kb.jobs)} ingestion jobs · {len(kb.models)} dbt models", "green")
    return f"""<div class="hero">
  <div class="brand">
    <div class="logo">◆</div>
    <div>
      <h1>Data Onboarding Agent</h1>
      <p>Describe the data you need. The agent asks for what's missing, checks the ingestion and transformation
      repositories to see what already exists and what has to be built, and drafts a User Story for the Data Team.</p>
    </div>
  </div>
  <div class="hero-pills"><span class="pill-label">Model</span>{model_pill}<span class="pill-label">Repos</span>{knowledge}</div>
</div>"""


# Step tracker. "complete" = every step done.
STEPS = [("describe", "Describe"), ("details", "Details"), ("feasibility", "Feasibility"), ("review", "Review"), ("story", "User Story")]
# Which step a running node belongs to, so the tracker moves while the agent works.
NODE_STEP = {
    "intake": "details",
    "notify": "details",
    "catalog_check": "feasibility",
    "feasibility": "feasibility",
    "investigate_source": "feasibility",
    "draft_us": "story",
    "summary": "story",
}


def _stage(ev: dict, values: dict) -> str:
    if ev["type"] == "done":
        return "complete"
    if ev["type"] == "approval":
        return "review"
    if ev["type"] == "question":
        return "feasibility" if values.get("gap") else "details"
    return "describe"


def _stepper_html(stage: str) -> str:
    keys = [k for k, _ in STEPS]
    current = len(keys) if stage == "complete" else keys.index(stage)
    items = []
    for i, (_, label) in enumerate(STEPS):
        if i < current:
            cls, mark = "done", "✓"
        elif i == current:
            # A feasibility question means a gap the user has to resolve.
            cls, mark = ("warn", "!") if stage == "feasibility" else ("active", str(i + 1))
        else:
            cls, mark = "todo", str(i + 1)
        items.append(f'<li class="step step-{cls}"><span class="dot">{mark}</span><span>{label}</span></li>')
    return f'<ol class="stepper">{"".join(items)}</ol>'


FIELD_NAMES = {
    "dataset_description": "What",
    "sources": "Sources",
    "date_range": "Date range",
    "eta": "Go-live (ETA)",
    "refresh_frequency": "Refresh",
    "grain": "Grain",
    "consumers": "Used by",
}


def _field_html(field: str, value) -> str:
    if field == "sources":
        return " ".join(_pill(s.upper() if len(s) <= 5 else s.title(), "blue") for s in value)
    if field == "date_range":
        return f"{_esc(value.get('start') or '?')} → {_esc(value.get('end') or 'now')}"
    return _esc(value)


def _request_html(values: dict) -> str:
    """Live card of the 7 required fields, filled as the conversation goes."""
    request, errors = values.get("request") or {}, values.get("errors") or {}
    filled = sum(1 for f in REQUIRED_FIELDS if request.get(f))
    rows = []
    for f in REQUIRED_FIELDS:
        body = _field_html(f, request[f]) if request.get(f) else '<span class="muted">Not provided yet</span>'
        if errors.get(f):
            body += f'<div class="err">{_esc(errors[f])}</div>'
        rows.append(f'<div class="prop"><dt>{FIELD_NAMES[f]}</dt><dd>{body}</dd></div>')
    pct = round(100 * filled / len(REQUIRED_FIELDS))
    foot = f'<div class="card-foot">{_esc(values["request_id"])}</div>' if values.get("request_id") else ""
    return f"""<div class="card">
  <div class="card-head"><span>Your request</span><span class="muted">{filled}/{len(REQUIRED_FIELDS)} details</span></div>
  <div class="bar"><div style="width:{pct}%"></div></div>
  <dl class="props">{"".join(rows)}</dl>{foot}
</div>"""


OVERALL = {
    "feasible": ("Feasible", "green"),
    "feasible_with_risks": ("Feasible with risks", "amber"),
    "gap": ("Gap found", "red"),
}


def _research_html(f: dict) -> str:
    parts = [f'<div class="meta">Web research: {f.get("pages_read", 0)} page(s) read, unverified.</div>']
    if f.get("summary"):
        parts.append(f'<div class="meta">{_esc(f["summary"])}</div>')
    for p in f.get("key_passages", [])[:3]:
        link = f' <a href="{_esc(p["url"])}" target="_blank" rel="noopener">source</a>' if str(p.get("url", "")).startswith("http") else ""
        parts.append(f'<div class="meta">• {_esc(p["topic"])}: “{_esc(p["text"])}”{link}</div>')
    if n := len(f.get("questions", [])):
        parts.append(f'<div class="meta">{n} question(s) for the Data Team added to the User Story.</div>')
    return "".join(parts)


KIND_PILL = {
    "existing_model": ("Existing dbt model", "green"),
    "landed": ("Landed, needs dbt model", "blue"),
    "new_job": ("New ingestion job", "amber"),
    "new_connection": ("New connection", "amber"),
}


def _source_html(src: dict, research: dict | None) -> str:
    name = f'<b>{_esc(src["source"])}</b>'
    rec = src.get("recommendation")
    if not rec:
        body = _pill("Needs investigation", "red") + " <span class=\"muted\">the platform can't onboard this source yet</span>"
        return f"<li>{name} {body}{_research_html(research) if research else ''}</li>"
    label, tone = KIND_PILL[rec["kind"]]
    meta = f'per <code>{_esc(rec["ref"])}</code>'
    if rec.get("tables"):
        meta = "landing: " + ", ".join(f"<code>{_esc(t)}</code>" for t in rec["tables"]) + " · " + meta
    return f'<li>{name} {_pill(label, tone)} <code>{_esc(rec["name"])}</code><div class="meta">{meta}</div></li>'


def _approval_html(ev: dict, title: str, note: str = "") -> str:
    """Feasibility card of a request waiting for approval: read-only for the requester, actionable in the review tab."""
    feas, research = ev["feasibility"], ev.get("research") or {}
    label, tone = OVERALL.get(feas["overall"], (feas["overall"], "neutral"))
    parts = [f'<div class="card-head"><span>{_esc(title)}</span>{_pill(label, tone)}</div>']
    if note:
        parts.append(f'<div class="meta note">{_esc(note)}</div>')
    if feas.get("data_already_available"):
        parts.append('<div class="callout">✅ This data already exists as a dbt model, so nothing new has to be ingested or built.</div>')
    parts.append('<div class="section-label">Sources</div><ul class="sources">')
    parts += [_source_html(s, research.get(s["source"])) for s in feas["sources"]]
    parts.append("</ul>")
    if feas.get("risks"):
        parts.append('<div class="section-label">Risks</div><ul class="risks">')
        parts += [f"<li>{_inline(r)}</li>" for r in feas["risks"]]
        parts.append("</ul>")
    return f'<div class="card flat">{"".join(parts)}</div>'


# ---------- chat ----------

WELCOME = """## 👋 What data do you need?
Describe it in your own words, in English or Vietnamese. The agent asks for anything missing
(source, date range, go-live date, refresh, grain, who uses it), checks feasibility,
and drafts a User Story for the Data Team to approve.

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
    "review": "Waiting for the Data Team. Type here only if you want to change your request…",
    "complete": "Describe another data request to start a new one…",
}

# What the "thinking" bubble says while each node runs.
NODE_STATUS = {
    "intake": "Reading your message…",
    "notify": "Notifying the Data Team…",
    "catalog_check": "Searching the dbt models…",
    "feasibility": "Checking feasibility…",
    "investigate_source": "Reading the web docs of sources the platform can't onboard yet…",
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
    elif ev["type"] == "approval":
        text = (
            "Thanks, I have everything I need and the feasibility check is done. Your request is now with the "
            "**Data Team** for review. This page updates when they approve it or ask for changes; "
            "you can also come back later from **Sessions**."
        )
    elif ev["type"] == "done":
        title = (values.get("outputs") or {}).get("title") or values.get("request_id", "")
        text = f"✅ Done! **{title}**\n\nUser Story created and the summary was sent to the Data Team. Preview or download it on the right."
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
    title = f"### ✅ {_esc(outputs.get('title') or values.get('request_id', ''))}\nUser Story created and the summary was sent to the Data Team."
    preview = Path(us).read_text(encoding="utf-8") if us else ""
    return title, preview, gr.update(value=us, visible=bool(us)), gr.update(value=summary, visible=bool(summary))


# Outputs of every chat handler, in this order:
# thread_state, chat, box, stepper, request_card, waiting_box, waiting_html,
# result_box, result_title, result_preview, us_download, summary_download, state_json, mark, poll_timer
N_OUT = 15
SKIP = tuple(gr.update() for _ in range(N_OUT))


def _mark(ev: dict, values: dict) -> str:
    """Fingerprint of a thread's progress; the review poll compares it to spot a Data Team decision."""
    return f"{len(values.get('messages') or [])}:{ev['type']}"


def _view(thread_id: str, history: list, ev: dict | None = None) -> tuple:
    """Every panel of the Request tab, from the thread's current state."""
    values = runner.state(thread_id) if thread_id else {}
    ev = ev or (runner.current_event(thread_id) if thread_id else {"type": "empty"})
    stage = _stage(ev, values)
    review, done = stage == "review", stage == "complete"
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
        gr.update(visible=done),
        *result,
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        _mark(ev, values),
        gr.Timer(active=review),  # poll for the Data Team's decision only while it is pending
    )


def _busy(thread_id: str, history: list, stepper=None) -> tuple:
    """While the agent runs: show the thinking bubble, clear the input, hide the waiting panel."""
    keep = gr.update()
    return (thread_id, history, gr.update(value=""), stepper or keep, keep, gr.update(visible=False), *[keep] * 9)


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


def on_send(message: str, thread_id: str, history: list):
    message = (message or "").strip()
    if not message:
        yield SKIP
        return
    history = history + [{"role": "user", "content": message}]
    ev = runner.current_event(thread_id) if thread_id else {"type": "empty"}
    if ev["type"] == "question":
        graph_input = Command(resume=message)
    elif ev["type"] == "approval":  # typing while approval is pending = edit request
        graph_input = Command(resume={"action": "edit", "comment": message})
    else:
        thread_id, graph_input = runner.new_request(message)
    yield from _run(thread_id, graph_input, history)


def on_example(evt: gr.SelectData, thread_id: str, history: list):
    text = evt.value.get("text", "") if isinstance(evt.value, dict) else str(evt.value)
    yield from on_send(text, thread_id, history)


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
        note = f"✏️ The **Data Team updated** your request: “{comment}”. The feasibility check was re-run."
    return _view(thread_id, history + [{"role": "assistant", "content": note}] + _reply(ev, values), ev)


# ---------- Data Team review ----------

def _review_queue() -> list[tuple[str, str]]:
    """Requests waiting for approval, newest first."""
    choices = []
    for tid in runner.threads(100):
        if runner.current_event(tid)["type"] != "approval":
            continue
        values = runner.state(tid)
        request = values.get("request") or {}
        desc = (request.get("dataset_description") or "")[:70]
        choices.append((f"{values.get('request_id', tid)} · {', '.join(request.get('sources', []))} · {desc}", tid))
    return choices


def on_review_refresh():
    choices = _review_queue()
    msg = f"**{len(choices)}** request(s) waiting for review." if choices else "Nothing waiting for review. 🎉"
    return gr.update(choices=choices, value=None), msg, gr.update(visible=False)


def on_review_open(thread_id: str):
    if not thread_id:
        return gr.update(visible=False), "", "", ""
    ev = runner.current_event(thread_id)
    if ev["type"] != "approval":
        gr.Warning("This request is no longer waiting for review. Refresh the list.")
        return gr.update(visible=False), "", "", ""
    values = runner.state(thread_id)
    return gr.update(visible=True), _request_html(values), _approval_html(ev, "Feasibility check"), ""


def on_review_decision(action: str):
    def handler(thread_id: str, comment: str):
        comment = (comment or "").strip()
        keep = gr.update()
        if not thread_id or runner.current_event(thread_id)["type"] != "approval":
            gr.Warning("This request is no longer waiting for review. Refresh the list.")
            return keep, keep, keep, keep, keep
        if action == "edit" and not comment:
            gr.Warning("Write what should change in the comment box first.")
            return keep, keep, keep, keep, keep
        runner.reply(thread_id, {"action": action, "comment": comment})
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


def on_unlock(key: str):
    if hmac.compare_digest((key or "").encode(), config.REVIEWER_KEY.encode()):
        return gr.update(visible=False), gr.update(visible=True), *on_review_refresh()[:2]
    gr.Warning("Wrong reviewer key.")
    return gr.update(), gr.update(), gr.update(), gr.update()


# ---------- sessions ----------

SESSION_STATUS = {"question": "waiting for the requester's answer", "approval": "waiting for Data Team review", "done": "done", "empty": "started"}


def _session_choices() -> list[tuple[str, str]]:
    choices = []
    for tid in runner.threads():
        values = runner.state(tid)
        if not values:
            continue
        sources = ", ".join((values.get("request") or {}).get("sources", [])) or "no source yet"
        status = SESSION_STATUS.get(runner.current_event(tid)["type"], "")
        choices.append((f"{values.get('request_id', tid)} · {sources} · {status}", tid))
    return choices


def on_refresh_sessions():
    return gr.update(choices=_session_choices(), value=None)


def on_resume(picked: str, pasted: str):
    thread_id = (pasted or "").strip() or (picked or "")
    values = runner.state(thread_id) if thread_id else {}
    if not values:
        gr.Warning("Session not found. Pick one from the list or check the thread_id.")
        return (*SKIP, gr.update())
    history = [{"role": m["role"], "content": m["content"]} for m in values.get("messages", [])]
    return (*_view(thread_id, history), gr.Tabs(selected="request"))


# ---------- LLM settings ----------

def on_refresh_models(host: str, api_key: str, current: str):
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


def on_test(host: str, api_key: str, model: str):
    if not model:
        return "Pick a model before testing."
    try:
        reply, secs = llm.ping(host, model, api_key)
    except Exception as exc:  # noqa: BLE001
        return f"❌ Error: {exc}"
    return f"✅ `{model}` replied in {secs:.1f}s: {reply}"


def on_apply(host: str, api_key: str, model: str):
    llm.configure(host, model, api_key)
    return f"**In use:** {llm.status()}", _header_html()


def on_disable(host: str):
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


def on_reload_repos():
    repos.reload()
    return _repos_md(), _header_html()


# ---------- layout ----------

THEME = gr.themes.Soft(
    primary_hue="indigo",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)

# One slim scrollbar inside the chat, no extra scroll on the wrapper.
CSS = """
#chat { overflow: hidden; }
#chat * { scrollbar-width: thin; scrollbar-color: var(--border-color-primary) transparent; }
#chat ::-webkit-scrollbar { width: 6px; }
#chat ::-webkit-scrollbar-thumb { background: var(--border-color-primary); border-radius: 3px; }
#chat ::-webkit-scrollbar-button { display: none; }
"""
# Shimmer on the title of a running "thought" block (the spinner is Gradio's own).
CSS += """
@keyframes thinking-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
#chat .thought-group .title:has(.loading-spinner) .md p {
  background: linear-gradient(90deg, var(--body-text-color-subdued) 35%, var(--body-text-color) 50%, var(--body-text-color-subdued) 65%);
  background-size: 200% 100%;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: thinking-shimmer 1.6s linear infinite;
}
"""
# Header, status pills, step tracker, cards.
CSS += """
.hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; padding: 4px 2px 6px; }
.hero .brand { display: flex; gap: 14px; align-items: flex-start; max-width: 780px; }
.hero .logo { flex: none; width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center;
  color: #fff; font-size: 20px; background: linear-gradient(135deg, #6366f1, #8b5cf6); }
.hero h1 { margin: 0; font-size: 22px; font-weight: 650; letter-spacing: -0.01em; }
.hero p { margin: 4px 0 0; color: var(--body-text-color-subdued); font-size: 14px; line-height: 1.5; }
.hero-pills { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding-top: 6px; }
.pill-label { font-size: 12px; color: var(--body-text-color-subdued); margin-left: 6px; }

.pill { display: inline-flex; align-items: center; padding: 1px 9px; border-radius: 999px; font-size: 12px; font-weight: 550;
  line-height: 20px; white-space: nowrap; border: 1px solid transparent; vertical-align: middle; }
.pill-neutral { background: rgba(100,116,139,.12); color: var(--body-text-color); border-color: rgba(100,116,139,.25); }
.pill-green { background: rgba(22,163,74,.10); color: #15803d; border-color: rgba(22,163,74,.30); }
.pill-amber { background: rgba(217,119,6,.10); color: #b45309; border-color: rgba(217,119,6,.30); }
.pill-red { background: rgba(220,38,38,.08); color: #b91c1c; border-color: rgba(220,38,38,.30); }
.pill-blue { background: rgba(79,70,229,.08); color: #4338ca; border-color: rgba(79,70,229,.25); }
.dark .pill-green { color: #4ade80; } .dark .pill-amber { color: #fbbf24; }
.dark .pill-red { color: #f87171; } .dark .pill-blue { color: #a5b4fc; }

.toolbar { align-items: center !important; margin-bottom: -4px; }
.stepper { display: flex; flex-wrap: wrap; align-items: center; list-style: none; margin: 0 !important; padding: 0 !important; row-gap: 6px; }
.stepper .step { display: flex; align-items: center; gap: 8px; margin: 0 !important; padding: 0 !important;
  font-size: 13px; color: var(--body-text-color-subdued); }
.stepper .step:not(:last-child)::after { content: ""; width: 26px; height: 2px; margin: 0 10px; border-radius: 2px; background: var(--border-color-primary); }
.stepper .dot { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700;
  border: 1.5px solid var(--border-color-primary); background: var(--block-background-fill); }
.stepper .step-done { color: var(--body-text-color); }
.stepper .step-done .dot { background: #6366f1; border-color: #6366f1; color: #fff; }
.stepper .step-done:not(:last-child)::after { background: #6366f1; }
.stepper .step-active, .stepper .step-warn { color: var(--body-text-color); font-weight: 600; }
.stepper .step-active .dot { border-color: #6366f1; color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,.18); }
.stepper .step-warn .dot { border-color: #d97706; color: #d97706; box-shadow: 0 0 0 3px rgba(217,119,6,.18); }

.card { border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 14px 16px; background: var(--block-background-fill); }
.card.flat { border: none; padding: 14px 16px 4px; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; margin-bottom: 10px; }
.muted { color: var(--body-text-color-subdued); font-weight: 400; font-size: 13px; }
.bar { height: 4px; border-radius: 4px; background: var(--border-color-primary); overflow: hidden; margin-bottom: 8px; }
.bar > div { height: 100%; background: #6366f1; transition: width .4s ease; }
.props { margin: 0; }
.prop { display: grid; grid-template-columns: 104px 1fr; gap: 10px; padding: 7px 0; border-top: 1px solid var(--border-color-primary); font-size: 13px; }
.prop:first-child { border-top: none; }
.prop dt { margin: 0; color: var(--body-text-color-subdued); }
.prop dd { margin: 0; word-break: break-word; }
.err { color: #dc2626; font-size: 12px; margin-top: 2px; }
.card-foot { margin-top: 8px; font-size: 12px; color: var(--body-text-color-subdued); font-family: var(--font-mono); }
.card code { font-size: 12px; }
.section-label { margin: 12px 0 4px; font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--body-text-color-subdued); }
.sources, .risks { list-style: none; margin: 0 !important; padding: 0 !important; font-size: 13px; }
.sources li { margin: 0 !important; padding: 7px 0; border-top: 1px solid var(--border-color-primary); }
.sources li:first-child { border-top: none; }
.risks li { position: relative; margin: 0 !important; padding: 3px 0 3px 20px; }
.risks li::before { content: "⚠"; position: absolute; left: 0; color: #d97706; }
.meta { margin-top: 3px; font-size: 12px; color: var(--body-text-color-subdued); }
.meta.note { margin: -4px 0 8px; }
.callout { margin-bottom: 4px; padding: 8px 10px; border-radius: 8px; font-size: 13px; background: rgba(22,163,74,.10); }

.review-box, .result-box { border: 1.5px solid #6366f1 !important; border-radius: 12px !important; overflow: hidden;
  box-shadow: 0 6px 20px rgba(79,70,229,.10); margin-bottom: 12px; }
.result-title { padding: 12px 16px 4px !important; }
.result-title h3 { margin: 0 0 6px; font-size: 16px; }
.us-preview { max-height: 50vh; overflow: auto; }

/* Example prompts in the empty chat as clickable cards. */
#chat .examples { gap: 10px !important; }
#chat .examples .example { border: 1px solid var(--border-color-primary) !important; border-radius: 12px !important;
  padding: 12px 14px !important; background: var(--block-background-fill) !important; text-align: left;
  transition: border-color .15s, box-shadow .15s, transform .15s; }
#chat .examples .example:hover { border-color: #6366f1 !important; box-shadow: 0 4px 14px rgba(79,70,229,.12); transform: translateY(-1px); }

/* Phone: step tracker shows dots only, plus the current step's name. */
@media (max-width: 640px) {
  .toolbar { flex-wrap: wrap !important; }
  .toolbar > * { min-width: 100% !important; }
  .stepper .step > span:last-child { display: none; }
  .stepper .step-active > span:last-child, .stepper .step-warn > span:last-child { display: inline; }
  .stepper .step:not(:last-child)::after { width: 12px; margin: 0 6px; }
}
"""


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Data Onboarding Agent") as demo:
        thread_state = gr.State("")
        header = gr.HTML(_header_html())

        with gr.Tabs(selected="request") as tabs:
            with gr.Tab("💬 Request", id="request"):
                with gr.Row(elem_classes="toolbar"):
                    stepper = gr.HTML(_stepper_html("describe"))
                    new_btn = gr.Button("＋ New request", size="sm", scale=0, min_width=140)
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        chat = gr.Chatbot(
                            elem_id="chat", show_label=False, height="56vh", buttons=[], placeholder=WELCOME, examples=EXAMPLES
                        )
                        box = gr.Textbox(
                            show_label=False, placeholder=PLACEHOLDERS["describe"], lines=1, max_lines=8, submit_btn="Send", autofocus=True
                        )
                    with gr.Column(scale=2):
                        # Read-only for the requester: the Data Team decides in the review tab.
                        with gr.Group(visible=False, elem_classes="review-box") as waiting_box:
                            waiting_html = gr.HTML()
                        with gr.Group(visible=False, elem_classes="result-box") as result_box:
                            result_title = gr.Markdown(elem_classes="result-title")
                            with gr.Row():
                                us_dl = gr.DownloadButton("⬇ User Story (.md)", variant="primary", size="sm", visible=False)
                                sum_dl = gr.DownloadButton("⬇ Summary (.md)", size="sm", visible=False)
                            with gr.Accordion("Preview User Story", open=False):
                                result_preview = gr.Markdown(elem_classes="us-preview")
                        request_card = gr.HTML(_request_html({}))

            with gr.Tab("🗂 Sessions", id="sessions") as sessions_tab:
                gr.Markdown("Sessions are saved automatically. Reopen one to continue where you left off, e.g. after a disconnect.")
                with gr.Row(equal_height=True):
                    session_dd = gr.Dropdown(label="Recent sessions", choices=[], scale=5)
                    refresh_sessions = gr.Button("↻ Refresh", scale=0, min_width=110)
                old_tid = gr.Textbox(label="…or paste a thread_id")
                resume_btn = gr.Button("Open session", variant="primary")
                thread_label = gr.Textbox(label="Current thread_id", interactive=False)

            with gr.Tab("🛡 Data Team review", id="review") as review_tab:
                with gr.Group(visible=bool(config.REVIEWER_KEY)) as review_gate:
                    gr.Markdown("### Data Team only\nEnter the reviewer key to approve requests.", elem_classes="result-title")
                    with gr.Row(equal_height=True):
                        reviewer_key = gr.Textbox(show_label=False, type="password", placeholder="Reviewer key", scale=4)
                        unlock_btn = gr.Button("Unlock", variant="primary", scale=1)
                with gr.Column(visible=not config.REVIEWER_KEY) as review_area:
                    review_count = gr.Markdown()
                    with gr.Row(equal_height=True):
                        review_dd = gr.Dropdown(label="Waiting for review", choices=[], scale=5)
                        review_refresh = gr.Button("↻ Refresh", scale=0, min_width=110)
                    review_msg = gr.Markdown()
                    review_us = gr.DownloadButton("⬇ User Story (.md)", size="sm", visible=False)
                    with gr.Row(equal_height=False, visible=False) as review_panel:
                        with gr.Column(scale=1):
                            review_request = gr.HTML()
                        with gr.Column(scale=1):
                            with gr.Group(elem_classes="review-box"):
                                review_feas = gr.HTML()
                                review_comment = gr.Textbox(
                                    show_label=False,
                                    placeholder="Comment: what should change? e.g. change eta to 2026-12-01 (needed for Request changes)",
                                )
                                with gr.Row():
                                    approve_btn = gr.Button("✓ Approve", variant="primary")
                                    edit_btn = gr.Button("✎ Request changes")

            with gr.Tab("⚙️ Settings", id="settings"):
                with gr.Row(equal_height=False):
                    with gr.Column():
                        gr.Markdown("### LLM\nRule-based works without a model; an LLM phrases questions and the User Story better.")
                        llm_status = gr.Markdown(f"**In use:** {llm.status()}")
                        host = gr.Textbox(label="Ollama host", value=config.OLLAMA_HOST, info="Local: http://localhost:11434 · Colab: URL tunnel (https://….trycloudflare.com)")
                        api_key = gr.Textbox(label="API key", type="password", value=config.OLLAMA_API_KEY, info="Only needed for the Colab-hosted model (behind the proxy)")
                        with gr.Row():
                            model = gr.Dropdown(
                                label="Model",
                                choices=[config.OLLAMA_MODEL] if config.OLLAMA_MODEL else [],
                                value=config.OLLAMA_MODEL or None,
                                allow_custom_value=True,
                                scale=3,
                            )
                            refresh_btn = gr.Button("🔄 Fetch models", scale=1)
                        with gr.Row():
                            test_btn = gr.Button("Test")
                            apply_btn = gr.Button("Apply", variant="primary")
                            disable_btn = gr.Button("Disable LLM")
                        llm_msg = gr.Markdown()
                    with gr.Column():
                        gr.Markdown(
                            "### Repositories\nThe agent reads the code of these repos to see what is already "
                            "ingested and modelled. Set `INGESTION_PATH` / `TRANSFORMATION_PATH` for local checkouts; "
                            "otherwise they are read from GitHub with `GITHUB_TOKEN`."
                        )
                        repos_md = gr.Markdown(_repos_md())
                        reload_btn = gr.Button("↻ Reload repositories", variant="primary")

            with gr.Tab("🔧 Debug", id="debug"):
                gr.Markdown("Raw agent state of the current session.")
                state_json = gr.Code(language="json")

        mark = gr.State("")
        poll_timer = gr.Timer(5, active=False)

        outputs =[thread_state, chat, box, stepper, request_card, waiting_box, waiting_html,
                   result_box, result_title, result_preview, us_dl, sum_dl, state_json, mark, poll_timer]
        assert len(outputs) == N_OUT
        # The chat shows its own "thinking" bubble, so hide Gradio's progress overlay.
        busy = {"show_progress": "hidden"}
        box.submit(on_send, [box, thread_state, chat], outputs, **busy)
        chat.example_select(on_example, [thread_state, chat], outputs, **busy)
        poll_timer.tick(on_poll, [thread_state, chat, mark], outputs, **busy)
        new_btn.click(lambda: _view("", []), None, outputs)
        thread_state.change(lambda t: t, thread_state, thread_label)

        review_tab.select(on_review_refresh, None, [review_dd, review_count, review_panel])
        review_refresh.click(on_review_refresh, None, [review_dd, review_count, review_panel])
        review_dd.change(on_review_open, review_dd, [review_panel, review_request, review_feas, review_msg])
        decision_out = [review_msg, review_us, review_panel, review_dd, review_comment]
        approve_btn.click(on_review_decision("approve"), [review_dd, review_comment], decision_out)
        edit_btn.click(on_review_decision("edit"), [review_dd, review_comment], decision_out)
        unlock_btn.click(on_unlock, reviewer_key, [review_gate, review_area, review_dd, review_count])
        reviewer_key.submit(on_unlock, reviewer_key, [review_gate, review_area, review_dd, review_count])

        sessions_tab.select(on_refresh_sessions, None, session_dd)
        refresh_sessions.click(on_refresh_sessions, None, session_dd)
        resume_btn.click(on_resume, [session_dd, old_tid], outputs + [tabs], **busy)

        refresh_btn.click(on_refresh_models, [host, api_key, model], [model, llm_msg])
        test_btn.click(on_test, [host, api_key, model], llm_msg)
        apply_btn.click(on_apply, [host, api_key, model], [llm_status, header])
        disable_btn.click(on_disable, host, [llm_status, header])
        reload_btn.click(on_reload_repos, None, [repos_md, header])
    return demo


def launch(**kwargs):
    """Build and launch the UI with its theme and CSS (use this from the notebook too)."""
    kwargs.setdefault("footer_links", ["gradio", "settings"])
    # Download buttons serve files from outputs/, which may live outside the working directory (OUTPUT_DIR).
    kwargs.setdefault("allowed_paths", [str(config.OUTPUT_DIR)])
    build_ui().launch(theme=THEME, css=CSS, **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="create a temporary public link (Colab)")
    parser.add_argument("--host", help="interface to bind, e.g. 0.0.0.0 in Codespaces/containers (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    launch(share=args.share, server_name=args.host, server_port=args.port)
