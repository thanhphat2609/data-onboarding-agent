# data-onboarding-agent

An AI agent that turns data requests into ready-to-build work: it gathers requirements from users step by step, checks existing data and source feasibility (availability, date range, ETA), notifies the data team on Teams, and drafts user stories with a pipeline proposal — with human approval at every key step.

Detailed plan: see `PLAN.md` (prototype plan).

> Everything is in English (UI, questions, User Story, Teams messages, code, docs). The agent still understands answers written in Vietnamese.

---

## Docs

- **[docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)**: a request from first message to User Story, for requesters and the Data Team
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: components, the agent graph, state, design rules, storage, deployment
- **[docs/PHASES.md](docs/PHASES.md)**: status of each phase, known issues, next steps

## Status

> Updated: 2026-10-23. Details per item: [docs/PHASES.md](docs/PHASES.md).

| Phase | Status |
|---|---|
| 0 – Setup | 🟡 Notebook written, not run on Colab; model not picked |
| 1 – Intake | ✅ |
| 2 – Knowledge | ✅ Read from the real ingestion and transformation repos (no demo data) |
| 3 – Feasibility | ✅ |
| 4 – Approval + Output | ✅ Approval by the Data Team in the review tab |
| 5 – Teams + Demo | 🟡 Mock works; real webhook, real requests and demo pending |
| Added: web research, Docker/Codespaces, UI redesign, repo knowledge | ✅ / 🟡 Docker not yet built for real |

---

## Architecture (short)

```
intake ⇄ ask_user ─▶ notify ─▶ catalog_check ─▶ feasibility ──gap──▶ intake
                                                    │
                                     investigate_source (sources the platform can't onboard yet)
                                                    │
                    approval (Data Team) ──request changes──▶ intake
                                                    │ approve
                                           draft_us ─▶ summary ─▶ END
```

Feasibility reads the code of the two platform repos: is the data already a dbt model in [data-onboarding-transformation](https://github.com/thanhphat2609/data-onboarding-transformation), already landing through a job in [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion), from an onboarded system (needs a new job), or from a supported source type (needs a new connection)? Decisions (routing, validation, feasibility) live in code; the optional LLM only helps with language. Web research is advisory. Nothing is drafted before the Data Team approves. Full picture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repo layout

```
data-onboarding-agent/
├── app.py                     # Web UI (Gradio)
├── notebooks/prototype.ipynb  # Colab: clone, Ollama, tool-calling test, host model via tunnel
├── agent/
│   ├── config.py              # paths + env vars
│   ├── state.py               # TypedDict state + request schema
│   ├── extraction.py          # field extraction (rule-based) + validation
│   ├── repos.py               # reads the ingestion + transformation repos (local checkout or GitHub)
│   ├── knowledge.py           # lookup_source, search_models (over repos.py)
│   ├── dbt_project.py         # dbt models from schema .yml files or manifest.json
│   ├── github.py              # GitHub REST: file tree + file content
│   ├── research.py            # web research for sources the platform can't onboard yet
│   ├── llm.py                 # Ollama client (optional, supports API key)
│   ├── graph.py               # build graph, SQLite checkpointer
│   ├── runner.py              # start/reply API for the UI and scripts
│   ├── nodes/                 # one file per node
│   ├── prompts/               # LLM prompts (.md)
│   └── integrations/teams.py  # Teams webhook (or mock)
├── scripts/
│   ├── ollama_auth_proxy.py   # API-key proxy in front of Ollama (runs on Colab)
│   ├── run_samples.py         # run scenarios / past requests, compare with expectations + team handling
│   └── test_teams_webhook.py  # send one test card to a Teams webhook
├── tests/scenarios/           # 5 scripted conversations against what the two repos contain today
├── docs/                      # architecture, how it works, phase status
├── infrastructure/            # Dockerfile + compose.yaml to run the UI (laptop / VM / Codespaces), see infrastructure/README.md
├── doc_links.yaml             # official doc links per source, used by web research
├── DEMO.md                    # team demo runbook
└── outputs/                   # results per request_id (gitignored)
```

### Where the knowledge comes from
There is no sample data in this repo. The agent reads the two platform repos on first use (and again on **⚙️ Settings → Reload repositories**):

| Repo | Files read | Tells the agent |
|---|---|---|
| data-onboarding-ingestion | `code/templates/sources/*.yaml` | Source types that can be onboarded (e.g. `sqlserver`) |
| | `pipelines/connections/*.yaml` | Systems already onboarded (e.g. `crm`) |
| | `pipelines/jobs/*.yaml` | Tables already landing in the lake (`<system>/<schema>/<table>`) |
| data-onboarding-transformation | `models/**/*.yml` (or `target/manifest.json`) | dbt models that already exist |

Set `INGESTION_PATH` / `TRANSFORMATION_PATH` to local checkouts (e.g. `../data-onboarding-ingestion`); otherwise they are read from GitHub with `GITHUB_TOKEN` (fine-grained, *Contents: Read-only* on both repos).

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

.venv\Scripts\python app.py                   # web UI at http://127.0.0.1:7860 (--share for a public link)
$env:INGESTION_PATH = "..\data-onboarding-ingestion"; $env:TRANSFORMATION_PATH = "..\data-onboarding-transformation"
.venv\Scripts\python scripts/run_samples.py   # run the 5 scenarios in tests/scenarios
```

Or activate the venv first (`.venv\Scripts\Activate.ps1`, or `source .venv/bin/activate` on Linux/Mac) and use plain `python`. If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Run with Docker / GitHub Codespaces

```bash
docker compose -f infrastructure/compose.yaml up -d --build
```
Then open http://127.0.0.1:7860. In GitHub Codespaces (Docker is preinstalled), open the forwarded port 7860 from the **PORTS** tab instead.

For settings (`.env` / Codespaces secrets), where data is stored, port visibility and troubleshooting, see [infrastructure/README.md](infrastructure/README.md).

## Deployment: model on Colab, web app on your machine

```
 Your machine                                    Google Colab (GPU T4)
┌──────────────────────────────┐   HTTPS +    ┌─────────────────────────────────────┐
│ python app.py (web UI)       │   API key    │ cloudflared tunnel                  │
│  ├─ ⚙️ LLM settings ──────────┼─────────────▶│  └─ scripts/ollama_auth_proxy.py    │
│  ├─ ⚙️ Repositories ─┐        │              │      └─ Ollama (qwen2.5 7B/14B)     │
│  └─ checkpoint, outputs      │              └─────────────────────────────────────┘
└─────────────────────┼────────┘
                      ▼ GitHub token (stays on your machine)
         ingestion + transformation repos (read on demand)
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
Open the **⚙️ Settings** tab, **LLM** column:
- **Ollama host**: paste the URL from Colab (for Ollama on your own machine use `http://localhost:11434`)
- **API key**: paste the key from Colab (leave empty for local Ollama)
- **🔄 Fetch models** → pick a model → **Test** → **Apply**
- **Disable LLM**: back to rule-based. The "In use" line shows what the agent is running on.

### Step 3 — Check the repositories
In the **⚙️ Settings** tab, **Repositories** column: where each repo was read from, the systems, jobs and dbt models found, and any error (e.g. a token that can't read a repo). **↻ Reload repositories** reads them again after a merge.

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
| `GITHUB_TOKEN` | (empty) | Fine-grained token, *Contents: Read-only* on both repos. Not needed with local checkouts. In Codespaces, export your own: the preset one only reads the codespace's repo |
| `INGESTION_REPO`, `INGESTION_REF` | `thanhphat2609/data-onboarding-ingestion`, `main` | |
| `TRANSFORMATION_REPO`, `TRANSFORMATION_REF` | `thanhphat2609/data-onboarding-transformation`, `main` | |
| `INGESTION_PATH`, `TRANSFORMATION_PATH` | (empty) | Local checkouts; win over GitHub |
| `TRANSFORMATION_DBT_DIR` | (empty) | dbt project folder inside the transformation repo |
| `CHECKPOINT_DB` | `./checkpoints.db` | |
| `OUTPUT_DIR` | `./outputs` | |
| `TEAMS_WEBHOOK_URL` | (empty) | Empty = mock, writes to a file |
| `REVIEWER_KEY` | (empty) | Key for the 🛡 Data Team review tab. Empty = open to everyone |
| `WEB_RESEARCH` | `1` | `0` = no web research for sources the platform can't onboard yet (questions are still generated) |
| `DOC_LINKS_PATH` | `./doc_links.yaml` | Known doc links per source |
| `RESEARCH_MAX_PAGES` | `3` | Pages read per source |

## After the prototype

Roadmap (VM + Postgres, Teams bot approvals, real tickets, Snowflake metadata, GitHub MCP): see [docs/PHASES.md](docs/PHASES.md#after-the-prototype).
