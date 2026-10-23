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
| 2 – Knowledge | 🟡 Tools done; only DEMO playbooks/catalog |
| 3 – Feasibility | ✅ |
| 4 – Approval + Output | ✅ Approval by the Data Team in the review tab |
| 5 – Teams + Demo | 🟡 Mock works; real webhook, real requests and demo pending |
| Added: web research, Docker/Codespaces, UI redesign | ✅ / 🟡 Docker not yet built for real |

---

## Architecture (short)

```
intake ⇄ ask_user ─▶ notify ─▶ catalog_check ─▶ feasibility ──gap──▶ intake
                                                    │
                                     investigate_source (sources without a playbook)
                                                    │
                    approval (Data Team) ──request changes──▶ intake
                                                    │ approve
                                           draft_us ─▶ summary ─▶ END
```

Decisions (routing, validation, feasibility) live in code; the optional LLM only helps with language. Web research is advisory. Nothing is drafted before the Data Team approves. Full picture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
│   ├── research.py            # web research for sources without a playbook
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
│   ├── run_samples.py         # run sample requests, compare with expectations + team handling
│   └── test_teams_webhook.py  # send one test card to a Teams webhook
├── sample_requests/           # REAL past requests (_template.yaml to start)
├── docs/                      # architecture, how it works, phase status
├── infrastructure/            # Dockerfile + compose.yaml to run the UI (laptop / VM / Codespaces), see infrastructure/README.md
├── doc_links.yaml             # official doc links per source, used by web research
├── DEMO.md                    # team demo runbook
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
Open the **⚙️ Settings** tab, **LLM** column:
- **Ollama host**: paste the URL from Colab (for Ollama on your own machine use `http://localhost:11434`)
- **API key**: paste the key from Colab (leave empty for local Ollama)
- **🔄 Fetch models** → pick a model → **Test** → **Apply**
- **Disable LLM**: back to rule-based. The "In use" line shows what the agent is running on.

### Step 3 — Sync the dbt catalog from GitHub
In the **⚙️ Settings** tab, **dbt catalog** column:
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
| `DBT_GITHUB_TOKEN` | (empty) | Token to read the dbt repo, used when the UI token field is empty. Wins over `GITHUB_TOKEN` (use this one in Codespaces) |
| `GITHUB_TOKEN` | (empty) | Fallback for `DBT_GITHUB_TOKEN` |
| `CHECKPOINT_DB` | `./checkpoints.db` | |
| `OUTPUT_DIR` | `./outputs` | |
| `TEAMS_WEBHOOK_URL` | (empty) | Empty = mock, writes to a file |
| `REVIEWER_KEY` | (empty) | Key for the 🛡 Data Team review tab. Empty = open to everyone |
| `WEB_RESEARCH` | `1` | `0` = no web research for sources without a playbook (questions are still generated) |
| `DOC_LINKS_PATH` | `./doc_links.yaml` | Known doc links per source |
| `RESEARCH_MAX_PAGES` | `3` | Pages read per source |
| `PLAYBOOK_DIR`, `CATALOG_PATH` | `playbooks/`, `catalog/dbt_models.json` (fallback `demo/`) | |

## After the prototype

Roadmap (VM + Postgres, Teams bot approvals, real tickets, Snowflake metadata, GitHub MCP): see [docs/PHASES.md](docs/PHASES.md#after-the-prototype).
