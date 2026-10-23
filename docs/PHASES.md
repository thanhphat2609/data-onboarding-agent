# Phases

Status of each phase of the prototype plan ([PLAN.md](../PLAN.md)) plus the work added after it.

> Updated: 2026-10-23. ✅ done and verified · 🟡 code exists, not yet run/verified in the real environment · ⬜ not started

## Overview

| Phase | Goal | Status |
|---|---|---|
| 0 – Setup | Repo, Colab notebook, model choice | 🟡 Notebook written, not run on Colab; model not picked |
| 1 – Intake | Collect the 7 details in a chat, persist sessions | ✅ |
| 2 – Knowledge | Playbooks + dbt catalog + lookup tools | 🟡 Tools done; only DEMO playbooks/catalog |
| 3 – Feasibility | Existing data, date-range gaps, access proposal | ✅ |
| 4 – Approval + Output | Data Team approval, User Story, summary | ✅ |
| 5 – Teams + Demo | Teams webhook, real past requests, demo | 🟡 Mock works; real webhook, real requests and demo pending |
| Added: Web research | Investigate sources without a playbook | ✅ |
| Added: Infrastructure | Docker / Codespaces | 🟡 Written, not yet built in real Docker |
| Added: UI redesign + Data Team review | Friendlier UI; approval by the Data Team only | ✅ Tested locally in a browser |

---

## Phase 0 – Setup
- ✅ Repo + folder structure
- 🟡 Notebook [notebooks/prototype.ipynb](../notebooks/prototype.ipynb): clone the private repo (token from Colab Secrets), install Ollama, pull models, test chat. **Written, not yet run on Colab**
- 🟡 Tool-calling test (`lookup_playbook`, `search_catalog`): the cell is in the notebook, not yet run
- ⬜ Pick 7B vs 14B: run the comparison cell on a Colab T4

## Phase 1 – Intake ✅
- ✅ `state.py` + request schema (7 required fields)
- ✅ `intake` node: asks for missing fields (max 3 per turn), validates the date range, ETA after today, valid refresh frequency
- ✅ Gradio web UI ([app.py](../app.py)), one session = one `thread_id` (redesigned later, see [UI redesign](#added-ui-redesign--data-team-review-2026-10-23))
- ✅ `SqliteSaver` checkpointer; "restart and continue" tested locally (new runner on the same `.db` file). 🟡 Not yet tested with a `.db` file on Google Drive

## Phase 2 – Knowledge
- 🟡 Playbooks: only **DEMO playbooks** for GA4 and AppsFlyer in `demo/playbooks/`. ⬜ The team writes real playbooks for the 7 sources in `playbooks/` (GSC in progress separately)
- ✅ dbt catalog sync from **GitHub (token)**, a local dbt project folder, or `manifest.json`, from the web UI (⚙️ Settings → dbt catalog) or [scripts/export_dbt_catalog.py](../scripts/export_dbt_catalog.py). Tested with the public repo `dbt-labs/jaffle_shop`. ⬜ The team's real dbt repo is not synced yet; still on the DEMO catalog
- ✅ Tools `lookup_playbook(source)` and `search_catalog(query)` ([agent/knowledge.py](../agent/knowledge.py))

## Phase 3 – Feasibility ✅
- ✅ `catalog_check` node: finds related dbt models per source
- ✅ `feasibility` node: compares the requested date range with each access method's `available_from` / `max_lookback_days`, warns about tight ETAs using `typical_lead_time_days`
- ✅ Gap (date range / source without a playbook) → back to `intake` to ask the user to accept or pick an alternative
- ✅ Data access proposal: existing model first → access methods from the playbook

## Phase 4 – Approval + Output ✅
- ✅ Approval pauses for the **Data Team** (`interrupt()` inside the node; equivalent to `interrupt_before=["approval"]`, but receives the decision payload on resume). Since 2026-10-23 the decision is made in the **🛡 Data Team review** tab, not by the requester. Request changes → back to intake to update the request → feasibility re-checked
- ✅ `draft_us` node: User Story from a template (title, user story, description, sources & feasibility, proposed pipeline, acceptance criteria, risks, information sources)
- ✅ `summary` node: final summary message
- ✅ Outputs written to `outputs/<request_id>/`: `request.json`, `feasibility.json`, `user_story.md`, `summary.md`

## Phase 5 – Teams + Demo
- 🟡 Teams Workflows webhook (notify + summary, Adaptive Card): code exists, **not tested with a real webhook**. Check a URL with `python scripts/test_teams_webhook.py "<url>"`. Without `TEAMS_WEBHOOK_URL` it mocks by writing `outputs/<request_id>/teams_messages.jsonl`. If the webhook call fails, the flow continues and the message goes to the same file with `webhook_error`
- 🟡 5 **DEMO** request scenarios in `demo/sample_requests/` (5/5 pass). ⬜ Need 3–5 real past requests in `sample_requests/` (copy [sample_requests/_template.yaml](../sample_requests/_template.yaml))
- ✅ Comparison tooling: a `team_handling` block in a sample (how the team actually handled it) is compared with the agent's result. Every run writes `outputs/eval/<timestamp>/report.md` (with a reviewer rating column) and `mistakes.csv` (one row per difference, with a `reviewer_notes` column). ⬜ Run it on real requests and review
- 🟡 Demo runbook: [DEMO.md](../DEMO.md). ⬜ Demo to the team

---

## Added: Web research for sources without a playbook ✅ (2026-10-20)
When a source has no playbook and the requester replies `ok`, the `investigate_source` step (after feasibility, before approval) looks up the source's public docs:
1. **Finds pages**: links the requester pasted in the chat → links in [doc_links.yaml](../doc_links.yaml) (kept by the team) → a DuckDuckGo search (`ddgs`, no API key) for the remaining slots (max 3 pages).
2. **Reads them** with plain HTTP and keeps sentences about data history/retention, quotas, auth and access methods. Pages that need JavaScript to render can't be read; they are listed as such.
3. **Writes**: a *Web research (unverified)* section and a *Questions for the Data Team* section in the User Story, the questions in the Teams summary card, a short note in the review panel, and a draft playbook `outputs/<request_id>/playbook_draft_<source>.yaml` (`review_status: draft`). With an LLM it also summarises and fills access methods in the draft; without one you get the key passages + standard questions.

The findings **never change the feasibility result** (the source stays "Needs investigation"). Only the source name + fixed keywords are sent to the search engine, never the request text. Turn it off with `WEB_RESEARCH=0`; `run_samples.py` keeps it off unless you pass `--web`.
To make the source "known": review the draft, set `review_status: reviewed`, save it as `playbooks/<source>.yaml`.

## Added: Infrastructure 🟡 (2026-10-23)
- ✅ [infrastructure/](../infrastructure/): `Dockerfile` (Python 3.12 slim, non-root, healthcheck), `compose.yaml` (localhost-only port, settings from env / `.env`, `outputs/` `catalog/` `playbooks/` bind-mounted), `.env.example`, README with how to open the UI
- ✅ Same command on a laptop, a VM and GitHub Codespaces (Docker is preinstalled there)
- ✅ `app.py --host`; `DBT_GITHUB_TOKEN` (Codespaces reserves `GITHUB_TOKEN`)
- ⬜ Build and run the image in real Docker / a codespace (no Docker was available when it was written)

## Added: UI redesign + Data Team review ✅ (2026-10-23)
- ✅ Tabs: **💬 Request**, **🗂 Sessions**, **🛡 Data Team review**, **⚙️ Settings**, **🔧 Debug**; admin tools are out of the requester's way
- ✅ Request tab: welcome screen with example prompts, step tracker (Describe → Details → Feasibility → Review → User Story, amber on gaps), live "Your request" card (x/7 details), status pills, User Story preview + download
- ✅ Approval by the Data Team only: review queue, request card + feasibility, Approve / Request changes; optional `REVIEWER_KEY`. The requester sees "Waiting for Data Team review" and their page updates on its own (5 s poll)
- ✅ Sessions tab lists recent sessions from the checkpointer
- ✅ Theme (Inter, indigo/slate), dark mode, phone width
- ✅ Verified in a headless browser: full GA4 flow, request changes → requester sees the update → approve → downloads; TikTok (no playbook) gap; Sessions reopen; reviewer key gate

---

## Known issues / backlog
- **"ok" can be taken as a field answer.** If a field is still pending (e.g. "Used by"), replying `ok` stores "ok" as its value. Seen 2026-10-23. Fix idea: ignore yes-words as values for free-text fields.
- **The Data Team can't ask the requester a question.** "Request changes" applies the comment as an edit to the request. A "send back with a question" action would need a new branch from `approval` to `ask_user`.
- **The reviewer key is a soft gate**, not authentication; the app has no logins. Real auth (SSO in front of the app, or a Teams bot for approvals) is post-prototype.
- **Chat doesn't auto-scroll** when the Data Team's decision arrives while the Request tab is in the background. Scroll down once.
- ✅ *Fixed 2026-10-20 by web research.* **Source without a playbook: "ok" did not trigger any investigation** (reported 2026-10-12, seen with GSC). Replying `ok` only recorded the risk and moved on, while the message read as if the agent would investigate. Reworded, and the `investigate_source` step was added. Workaround that still applies: add `playbooks/<source>.yaml` and the gap disappears for that source.

## Next steps
1. Run the notebook on Colab: tool-calling test, pick a model, host the model for the web app.
2. Build and run the Docker image (`docker compose -f infrastructure/compose.yaml up -d --build`), locally or in a codespace.
3. Sync the catalog from the real dbt repo (⚙️ Settings → dbt catalog); the team writes real playbooks in `playbooks/`.
4. Write real past requests in `sample_requests/` (from `_template.yaml`, including `team_handling`), run `python scripts/run_samples.py sample_requests`, review `report.md` / `mistakes.csv`.
5. Hook up the real Teams webhook (`scripts/test_teams_webhook.py` first).
6. Set `REVIEWER_KEY` and demo to the team following [DEMO.md](../DEMO.md): one person as requester, one as the Data Team.

## After the prototype
From [PLAN.md](../PLAN.md):
1. Run on a VM with Docker (the compose file is ready); checkpointer → Postgres
2. Model: Ollama/vLLM on a GPU VM, or an LLM API approved by the company
3. Teams bot to approve directly in the thread (replaces the review tab + key)
4. Create real User Stories in Azure DevOps / Jira
5. Read Snowflake metadata directly instead of a manually exported catalog

**MCP for GitHub:** the catalog is currently read straight through the GitHub API (more reliable with small models). Once tool calling is stable (after Phase 0), a GitHub MCP server could let the agent read a model's SQL when it needs more detail (e.g. "does this model filter on X?").
