"""HTML pieces of the web UI: header, step tracker, request card, feasibility and research panels."""
import html
import re

from agent import repos
from agent.llm import client as llm
from agent.state import REQUIRED_FIELDS

# ---------- HTML helpers ----------

def _esc(text) -> str:
    """HTML-escaped text."""
    return html.escape(str(text or ""))


def _inline(text: str) -> str:
    """Escape, then render the `code` and **bold** used in the agent's messages."""
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", _esc(text))
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)


def _pill(text: str, tone: str = "neutral") -> str:
    """A small coloured label."""
    return f'<span class="pill pill-{tone}">{_esc(text)}</span>'


def _header_html() -> str:
    """The page header, with the model in use."""
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
STEPS = [("describe", "Describe"), ("details", "Details"), ("feasibility", "Feasibility"), ("draft", "Draft"), ("review", "Review"),
         ("story", "User Story")]
# Which step a running node belongs to, so the tracker moves while the agent works.
NODE_STEP = {
    "intake": "details",
    "requester_review": "draft",
    "notify": "review",
    "catalog_check": "feasibility",
    "feasibility": "feasibility",
    "investigate_source": "feasibility",
    "draft_us": "story",
    "summary": "story",
}


def _stage(ev: dict, values: dict) -> str:
    """The step of the stepper that a request is at, from its state."""
    if ev["type"] == "done":
        return "complete"
    if ev["type"] == "draft":
        return "draft"
    if ev["type"] == "approval":
        return "review"
    if ev["type"] == "question":
        return "feasibility" if values.get("gap") else "details"
    return "describe"


def _stepper_html(stage: str) -> str:
    """The stepper (describe, check, review, approval, done) with the current step marked."""
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
    """One request field as HTML; sources become labels."""
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
    """The web research of a source as HTML: counts, links and findings."""
    searched = f'{len(f.get("searches", []))} search(es) in {f.get("rounds") or 1} round(s), ' if f.get("searches") else ""
    parts = [f'<div class="meta">Web research: {searched}{f.get("pages_read", 0)} page(s) read, unverified.</div>']
    if f.get("summary"):
        parts.append(f'<div class="meta">{_esc(f["summary"])}</div>')
    for i, link in enumerate(f.get("links", []), 1):
        parts.append(
            f'<div class="meta">{i}. <a href="{_esc(link["url"])}" target="_blank" rel="noopener">{_esc(link["title"][:80])}</a>'
            f' <span class="muted">({_esc(", ".join(link["found_for"]))})</span></div>'
        )
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
    """One source with its feasibility recommendation and research."""
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
