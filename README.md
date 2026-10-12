# data-onboarding-agent

An AI agent that turns data requests into ready-to-build work: it gathers requirements from users step by step, checks existing data and source feasibility (availability, date range, ETA), notifies the data team on Teams, and drafts user stories with a pipeline proposal — with human approval at every key step.

Detailed plan: see `PLAN.md` (prototype plan).

> The agent talks to users in Vietnamese (questions, UI labels, User Story, Teams messages). Code, comments and docs are in English.

---

## Phase status

> Updated: 2026-10-12. ✅ done · 🟡 code exists, not yet run/verified in the real environment · ⬜ not started

### Phase 0 – Setup
- ✅ Repo + folder structure
- 🟡 Notebook [notebooks/prototype.ipynb](notebooks/prototype.ipynb): clone the private repo (token from Colab Secrets), install Ollama, pull models, test chat — **written, not yet run on Colab**
- 🟡 Tool-calling test (`lookup_playbook`, `search_catalog`) — cell is in the notebook, not yet run
- ⬜ Pick 7B vs 14B — run the comparison cell on a Colab T4

### Phase 1 – Intake ✅
- ✅ `state.py` + request schema (7 required fields)
- ✅ `intake` node: asks for missing fields (max 3 per turn), validates date range, ETA after today, valid refresh frequency
- ✅ Gradio web UI ([app.py](app.py)): one session = one `thread_id`, Approve / Edit buttons, resume an old session by `thread_id`, **LLM settings** panel to pick host/model/API key in the app (can call a Colab-hosted model)
- ✅ `SqliteSaver` checkpointer, "restart and continue" tested locally (new runner on the same `.db` file). 🟡 Not yet tested with a `.db` file on Google Drive.

### Phase 2 – Knowledge
- 🟡 Playbooks: only **DEMO playbooks** for GA4 and AppsFlyer in `demo/playbooks/`. ⬜ Team writes real playbooks for the 7 sources in `playbooks/` (GSC in progress separately).
- ✅ dbt catalog sync from **GitHub (token)**, a local dbt project folder, or `manifest.json` — from the web UI (📦 dbt catalog) or [scripts/export_dbt_catalog.py](scripts/export_dbt_catalog.py). Tested with the public repo `dbt-labs/jaffle_shop`. ⬜ Team's real dbt repo not synced yet — still on the DEMO catalog.
- ✅ Tools `lookup_playbook(source)` and `search_catalog(query)` ([agent/knowledge.py](agent/knowledge.py))

### Phase 3 – Feasibility ✅
- ✅ `catalog_check` node: finds related dbt models per source
- ✅ `feasibility` node: compares the requested date range with each access method's `available_from` / `max_lookback_days`, warns about tight ETAs using `typical_lead_time_days`
- ✅ Gap (date range / source without a playbook) → back to `intake` to ask the user to accept or pick an alternative
- ✅ Data access proposal: existing model first → access methods from the playbook

### Phase 4 – Approval + Output ✅
- ✅ Approval pauses for a reviewer (uses `interrupt()` inside the node — equivalent to `interrupt_before=["approval"]`, but receives the Approve/Edit payload on resume). Edit → back to intake to update the request → feasibility re-checked.
- ✅ `draft_us` node: User Story from a template (title, user story, description, sources & feasibility, proposed pipeline, acceptance criteria, risks, information sources)
- ✅ `summary` node: final summary message
- ✅ Outputs written to `outputs/<request_id>/`: `request.json`, `feasibility.json`, `user_story.md`, `summary.md`

### Phase 5 – Teams + Demo
- 🟡 Teams Workflows webhook (notify + summary, Adaptive Card) — code exists, **not tested with a real webhook**. Without `TEAMS_WEBHOOK_URL` it mocks by writing `outputs/<request_id>/teams_messages.jsonl`.
- 🟡 5 **DEMO** request scenarios in `demo/sample_requests/` (5/5 pass). ⬜ Need 3–5 real past requests (same YAML format, in their own folder, e.g. `sample_requests/`).
- ⬜ Compare agent output with how the team actually handled them, log the mistakes
- ⬜ Demo to the team

### Next steps
1. Run the notebook on Colab: tool-calling test, pick a model, host the model for the local web app (step 4).
2. Sync the catalog from the real dbt repo (📦 dbt catalog); team writes real playbooks in `playbooks/`.
3. Write real past requests in the `demo/sample_requests/` format, run `python scripts/run_samples.py <folder>`.
4. Hook up the real Teams webhook.

---

## Architecture

```
intake ⇄ ask_user   (ask until all fields are filled / gaps are resolved)
  │
  ▼
notify ─▶ catalog_check ─▶ feasibility ──gap──▶ intake
                               │
                               ▼
                           approval ──edit──▶ intake
                               │ approve
                               ▼
                           draft_us ─▶ summary ─▶ END
```

- **Branching and feasibility logic live entirely in code.** The LLM only extracts fields from free-text answers, phrases questions, and writes the User Story title/description.
- **The LLM is optional**: without `OLLAMA_MODEL` (or if Ollama is down) the agent uses a rule-based parser, so local demos run without a GPU.
- Every proposal in the User Story cites the playbook/catalog it came from.

## Repo layout

```
data-onboarding-agent/
├── app.py                     # Web UI (Gradio)
├── notebooks/prototype.ipynb  # Colab: clone, Ollama, tool-calling test, host model via tunnel
├── agent/
│   ├── config.py              # paths + env vars
│   ├── state.py               # TypedDict state + request schema
│   ├── extraction.py          # field extraction (rule-based) + validation
│   ├── knowledge.py           # lookup_playbook, search_catalog
│   ├── llm.py                 # Ollama client (optional, supports API key)
│   ├── catalog_sync.py        # build catalog from GitHub / local / manifest
│   ├── graph.py               # build graph, SQLite checkpointer
│   ├── runner.py              # start/reply API for the UI and scripts
│   ├── nodes/                 # one file per node
│   ├── prompts/               # LLM prompts (.md)
│   └── integrations/teams.py  # Teams webhook (or mock)
├── playbooks/                 # REAL playbooks (empty for now, see playbooks/README.md)
├── catalog/                   # REAL dbt catalog (empty until synced)
├── demo/                      # ⚠️ SAMPLE DATA — delete the whole folder once real data exists
│   ├── playbooks/             #   ga4.yaml, appsflyer.yaml
│   ├── catalog/               #   dbt_models.json
│   └── sample_requests/       #   5 scripted conversations + expected results
├── scripts/
│   ├── export_dbt_catalog.py  # catalog sync from the command line
│   ├── ollama_auth_proxy.py   # API-key proxy in front of Ollama (runs on Colab)
│   └── run_samples.py         # run sample requests and compare with expectations
└── outputs/                   # results per request_id (gitignored)
```

### Real data vs demo data
The agent prefers `playbooks/` and `catalog/dbt_models.json`. Only when they are empty does it fall back to `demo/`, and then every feasibility result carries a "DEMO data" warning. Other paths can be set with `PLAYBOOK_DIR` and `CATALOG_PATH`.

When moving the code to the company repo: delete the `demo/` folder.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

.venv\Scripts\python app.py                   # web UI at http://127.0.0.1:7860 (--share for a public link)
.venv\Scripts\python scripts/run_samples.py   # run the 5 demo scenarios
```

Or activate the venv first (`.venv\Scripts\Activate.ps1`, or `source .venv/bin/activate` on Linux/Mac) and use plain `python`. If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Deployment: model on Colab, web app on your machine

```
 Your machine                                    Google Colab (GPU T4)
┌──────────────────────────────┐   HTTPS +    ┌─────────────────────────────────────┐
│ python app.py (web UI)       │   API key    │ cloudflared tunnel                  │
│  ├─ ⚙️ LLM settings ──────────┼─────────────▶│  └─ scripts/ollama_auth_proxy.py    │
│  ├─ 📦 dbt catalog ─┐         │              │      └─ Ollama (qwen2.5 7B/14B)     │
│  └─ checkpoint, outputs      │              └─────────────────────────────────────┘
└─────────────────────┼────────┘
                      ▼ GitHub token (stays on your machine)
               dbt GitHub repo  ──▶  catalog/dbt_models.json
```

Ollama has no authentication, so on Colab `scripts/ollama_auth_proxy.py` sits in front of it: it requires an API key and only allows read/chat APIs (pull/delete are blocked).

> ⚠️ Free-tier Colab restricts using the runtime as a web service / accessing it outside the notebook UI. Calling the model from your machine through a tunnel may break the terms and get the session cut off — read the Colab FAQ before using it regularly. Fallbacks: run the web app on Colab too (option B in the notebook), or run Ollama on a machine with a GPU / use an LLM API approved by the company.

### Step 1 — Host the model on Colab
1. Create a fine-grained GitHub token with **Contents: Read-only** on this repo only. In Colab, add it under 🔑 **Secrets** as `GITHUB_TOKEN` and turn on *Notebook access* (the repo is private; the token never goes into the notebook).
2. Open [notebooks/prototype.ipynb](notebooks/prototype.ipynb) on Colab (GPU T4 runtime) — *File → Upload notebook*, or *File → Open notebook → GitHub* with *Include private repos*.
3. Run steps 1 → 4. Step 4 prints:
   ```
   Ollama host : https://xxxx.trycloudflare.com
   API key     : ....
   ```
Keep the Colab tab open. The URL changes every time the cell is re-run.

### Step 2 — Open the web app on your machine
```powershell
.venv\Scripts\python app.py   # http://127.0.0.1:7860
```
Open **⚙️ LLM settings** in the right column:
- **Ollama host**: paste the URL from Colab (for Ollama on your own machine use `http://localhost:11434`)
- **API key**: paste the key from Colab (leave empty for local Ollama)
- **🔄 Lấy danh sách** (fetch models) → pick a model → **Test** → **Áp dụng** (apply)
- **Tắt LLM** (disable LLM): back to rule-based. The "Đang dùng" (in use) line shows what the agent is running on.

### Step 3 — Sync the dbt catalog from GitHub
Open **📦 dbt catalog**:
- **GitHub**: enter the repo `owner/name`, branch, the dbt project folder inside the repo (if not at the root), and a token. Click **Sync catalog**.
- **Local**: enter the path of a dbt project folder, or a `manifest.json` file.

`target/manifest.json` is used if present; otherwise the schema `.yml` files under `models/` are read (model name, description, columns, tags, `meta`). The result is written to `catalog/dbt_models.json`, and the agent switches to it from the demo catalog right away.

GitHub token: use a **fine-grained token with `Contents: Read-only`** on the dbt repo only. It is used only during the sync and never written to disk. To avoid re-entering it, set the `GITHUB_TOKEN` env var and leave the token field empty.

Command-line sync also works:
```bash
python scripts/export_dbt_catalog.py --github owner/repo --ref main --subdir dbt   # token from GITHUB_TOKEN
python scripts/export_dbt_catalog.py --project-dir ../my-dbt-project
python scripts/export_dbt_catalog.py --manifest ../my-dbt-project/target/manifest.json
```

### Defaults at startup
Settings chosen in the UI are lost when the app stops. To have them preset, set env vars before starting:
```powershell
$env:OLLAMA_HOST = "https://xxxx.trycloudflare.com"; $env:OLLAMA_API_KEY = "..."; $env:OLLAMA_MODEL = "qwen2.5:7b"
.venv\Scripts\python app.py
```

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Local Ollama URL, or the tunnel URL from Colab |
| `OLLAMA_API_KEY` | (empty) | Key for the proxy on Colab |
| `OLLAMA_MODEL` | (empty) | e.g. `qwen2.5:7b`. Empty = rule-based |
| `GITHUB_TOKEN` | (empty) | Token to read the dbt repo, used when the UI token field is empty |
| `CHECKPOINT_DB` | `./checkpoints.db` | |
| `OUTPUT_DIR` | `./outputs` | |
| `TEAMS_WEBHOOK_URL` | (empty) | Empty = mock, writes to a file |
| `PLAYBOOK_DIR`, `CATALOG_PATH` | `playbooks/`, `catalog/dbt_models.json` (fallback `demo/`) | |

## After the prototype

From `PLAN.md`: move to a VM (Docker) + Postgres checkpointer, a Teams bot to approve inside the thread, create real User Stories in Azure DevOps/Jira, read Snowflake metadata directly.

**MCP for GitHub:** the catalog is currently read straight through the GitHub API (more reliable with small models). Once tool calling is stable (after Phase 0), a GitHub MCP server could let the agent read a model's SQL when it needs more detail (e.g. "does this model filter on X?").
