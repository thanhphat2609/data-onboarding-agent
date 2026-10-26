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

> Updated: 2026-10-26. Details per item: [docs/PHASES.md](docs/PHASES.md).

| Phase | Status |
|---|---|
| 0 – Setup | 🟡 Notebook written, not run on Colab; model not picked |
| 1 – Intake | ✅ |
| 2 – Knowledge | ✅ Read from the real ingestion and transformation repos (no demo data) |
| 3 – Feasibility | ✅ |
| 4 – Approval + Output | ✅ Approval by the Data Team in the review tab |
| 5 – Teams + Demo | 🟡 Mock works; real webhook, real requests and demo pending |
| Added: web research, UI redesign, repo knowledge | ✅ |
| Added: Docker/Codespaces, PostgreSQL sessions, login with roles | 🟡 Runs in Codespaces (v0.7.0); a full request + approval in Docker still to check |
| Added: SearXNG + Trafilatura for web research | 🟡 Checked offline; real searches in a codespace pending |
| Added: CI/CD | 🟡 CI green on every push; the Deploy workflow waits for VM 1 |
| Added: web research fix (clean source name, plain queries, two tools) + "where does it come from?" | 🟡 Checked offline end to end; real searches in a codespace pending |
| Next: 3 User Stories per request (spike, ingestion, transformation) | ⬜ Planned, see [docs/PHASES.md](docs/PHASES.md#next-phase-3-user-stories-per-request) |

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
├── notebooks/
│   ├── prototype.ipynb        # Colab: clone, Ollama, tool-calling test, host model via tunnel
│   └── ollama_auth_proxy.py   # API-key proxy in front of Ollama (run by the notebook on Colab)
├── agent/
│   ├── config.py              # paths + env vars
│   ├── state.py               # TypedDict state + request schema
│   ├── auth.py                # login: Data Team accounts, requester self-registration (scrypt hashes)
│   ├── workflow/              # the LangGraph flow
│   │   ├── graph.py           #   build graph, PostgreSQL / SQLite checkpointer
│   │   ├── runner.py          #   start/reply API for the UI and scripts
│   │   ├── sessions.py        #   sessions table: owner, status, reviewer per thread_id
│   │   ├── extraction.py      #   field extraction (rule-based) + validation
│   │   ├── evaluate.py        #   run past requests, compare with expectations + team handling
│   │   └── nodes/             #   one file per node
│   ├── repos/                 # knowledge from the ingestion + transformation repos (local checkout or GitHub)
│   │   ├── __init__.py        #   load / get / reload, parse templates, connections, jobs
│   │   ├── dbt_project.py     #   dbt models from schema .yml files or manifest.json
│   │   ├── github.py          #   GitHub REST: file tree + file content
│   │   └── lookup.py          #   lookup_source, search_models
│   ├── research/              # sources the platform can't onboard yet
│   │   ├── investigate.py     #   web research in rounds: top 5 links, key passages, questions, draft notes
│   │   └── websearch/         #   Python port of web-search-mcp: SearXNG + key-less engines, page text, MCP server
│   ├── llm/                   # optional Ollama client (client.py) + prompts/
│   └── integrations/teams.py  # Teams webhook (or mock); `python -m agent.integrations.teams <url>` sends a test card
├── docs/                      # architecture, how it works, phase status
├── infrastructure/            # Dockerfile, non-prod/ compose (laptop / Codespaces), prod/ (VM 1, draft), postgres/ init, searxng/ settings; see infrastructure/README.md
├── .github/workflows/         # ci.yml on every push, deploy.yml run by hand (the approval) once VM 1 exists
├── requirements.txt           # dependencies (Chromium for the headless browser is a separate, optional download)
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

Set `INGESTION_PATH` / `TRANSFORMATION_PATH` to local checkouts (e.g. `../data-onboarding-ingestion`); otherwise they are read from GitHub with `PLATFORM_GITHUB_TOKEN` or `GITHUB_TOKEN` (fine-grained, *Contents: Read-only* on both repos; use `PLATFORM_GITHUB_TOKEN` in Codespaces).

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

.venv\Scripts\python app.py                   # web UI at http://127.0.0.1:7860 (--share for a public link)
.venv\Scripts\python -m agent.workflow.evaluate <folder>   # replay past requests (YAML) and compare
```

Or activate the venv first (`.venv\Scripts\Activate.ps1`, or `source .venv/bin/activate` on Linux/Mac) and use plain `python`. If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Run with Docker / GitHub Codespaces

```bash
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
```
Then open http://127.0.0.1:7860. In GitHub Codespaces (Docker is preinstalled), open the forwarded port 7860 from the **PORTS** tab instead.

Three containers start: `app` (web UI and agent), `postgres` (sessions, plus the `airflow` and `platform` databases that data-onboarding-ingestion uses on the same host) and `searxng` (web search). Prod on VM 1 runs the same three from `infrastructure/prod/`; CI runs on every push and the Deploy workflow is run by hand ([infrastructure/prod/README.md](infrastructure/prod/README.md)).

For settings (`.env` / Codespaces secrets), where data is stored, port visibility and troubleshooting, see [infrastructure/README.md](infrastructure/README.md).

## Web search and the MCP server

Web research uses two tools from [agent/research/websearch/](agent/research/websearch/), a Python port of [web-search-mcp](https://github.com/mrkrsl/web-search-mcp) (MIT): **`web_search`** (title, URL, snippet per result) and **`web_fetch`** (main text of one page). Search goes to the self-hosted **SearXNG** container first (Docker setups, `SEARXNG_URL`), then to Brave (headless browser) and DuckDuckGo (`ddgs`); no API keys. Pages are read over HTTP with **Trafilatura** for the main text, or in a headless browser when they need JavaScript.

For each source the platform can't onboard yet, research runs in up to 2 rounds (one search per topic, then follow-ups on the docs site for what is still missing) and hands the Data Team the **top 5 links**, key passages, questions and draft source notes. All of it is unverified and never changes the feasibility result ([details](docs/ARCHITECTURE.md#web-search)).

- **Headless browser (optional):** `python -m playwright install chromium` once (the Playwright package is in `requirements.txt`). Without it, Brave is skipped (search uses SearXNG, then DuckDuckGo through `ddgs`) and JavaScript-only pages stay unreadable. Docker: `WITH_BROWSER=true`.
- **MCP server** with the same two tools (`web_search`, `web_fetch`), for LM Studio, Claude Desktop or other MCP clients:
  ```json
  {"mcpServers": {"web-search": {"command": "python", "args": ["-m", "agent.research.websearch.mcp_server"],
                                 "cwd": "/path/to/data-onboarding-agent"}}}
  ```

Key-less search (SearXNG included) scrapes public search engines, so they can rate-limit a network for a while. SearXNG makes it rarer by asking several engines at once. When nothing comes back, the agent says "web search found nothing", gives a ready-made search link instead of the top links, and still asks the Data Team its standard questions. When results come back but none names the source, it says so instead: that points to a wrong source name, not a blocked engine.

## Deployment: model on Colab, web app on your machine

```
 Your machine                                    Google Colab (GPU T4)
┌──────────────────────────────┐   HTTPS +    ┌─────────────────────────────────────┐
│ python app.py (web UI)       │   API key    │ cloudflared tunnel                  │
│  ├─ ⚙️ LLM settings ──────────┼─────────────▶│  └─ notebooks/ollama_auth_proxy.py  │
│  ├─ ⚙️ Repositories ─┐        │              │      └─ Ollama (qwen2.5 7B/14B)     │
│  └─ checkpoint, outputs      │              └─────────────────────────────────────┘
└─────────────────────┼────────┘
                      ▼ GitHub token (stays on your machine)
         ingestion + transformation repos (read on demand)
```

Ollama has no authentication, so on Colab `notebooks/ollama_auth_proxy.py` sits in front of it: it requires an API key and only allows read/chat APIs (pull/delete are blocked).

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
| `GITHUB_TOKEN` | (empty) | Fine-grained token, *Contents: Read-only* on both repos. Not needed with local checkouts |
| `PLATFORM_GITHUB_TOKEN` | (empty) | Same token under a name that wins over `GITHUB_TOKEN`. Use it in Codespaces, where `GITHUB_TOKEN` is preset for the codespace's own repo and a secret can't be named `GITHUB_*` |
| `INGESTION_REPO`, `INGESTION_REF` | `thanhphat2609/data-onboarding-ingestion`, `main` | |
| `TRANSFORMATION_REPO`, `TRANSFORMATION_REF` | `thanhphat2609/data-onboarding-transformation`, `main` | |
| `INGESTION_PATH`, `TRANSFORMATION_PATH` | (empty) | Local checkouts; win over GitHub |
| `TRANSFORMATION_DBT_DIR` | (empty) | dbt project folder inside the transformation repo |
| `DATABASE_URL` | (empty) | PostgreSQL for sessions, e.g. `postgresql://agent:…@postgres:5432/onboarding_agent` (set by Docker compose). Empty = SQLite at `CHECKPOINT_DB` |
| `CHECKPOINT_DB` | `./checkpoints.db` | SQLite file when `DATABASE_URL` is empty |
| `OUTPUT_DIR` | `./outputs` | |
| `TEAMS_WEBHOOK_URL` | (empty) | Empty = mock, writes to a file |
| `ACCOUNTS` | (empty) | Web UI logins, `user:password` pairs separated by commas; usually only the Data Team (other emails self-register on first sign-in). Empty = no login, every tab open |
| `ACCOUNTS_FILE` | (empty) | Same, one `user:password` per line (e.g. a Docker secret); `#` starts a comment |
| `DATA_TEAM` | `data.team@gmail.com` | Accounts with full access (review, Settings, Debug, every session). Others are requesters: Request + their own Sessions |
| `WEB_RESEARCH` | `1` | `0` = no web research for sources the platform can't onboard yet (questions are still generated) |
| `RESEARCH_MAX_PAGES` | `8` | Pages read per source, across all rounds |
| `RESEARCH_ROUNDS` | `2` | Research rounds per source: planned searches, then follow-up searches on the docs site for topics still without evidence |
| `RESEARCH_TIME_BUDGET_S` | `180` | Seconds of research per source before it stops with what it has |
| `WEBSEARCH_BROWSER` | `auto` | `off` = never use the headless browser, even when Playwright is installed |
| `SEARXNG_URL` | empty (compose: `http://searxng:8080`) | Self-hosted SearXNG, the first search engine for web research; empty = only Brave (with the browser) and DuckDuckGo (`ddgs`) |
| `RELEVANCE_THRESHOLD`, `ENABLE_RELEVANCE_CHECKING`, `FORCE_MULTI_ENGINE_SEARCH` | `0.3`, `true`, `false` | Search result quality check (same as web-search-mcp) |
| `MAX_CONTENT_LENGTH`, `DEFAULT_TIMEOUT` | `500000`, `6000` (ms) | Page content limit and fetch timeout |

## After the prototype

Roadmap (prod on VM 1, a production model, Teams bot approvals, real tickets, lake metadata, GitHub MCP): see [docs/PHASES.md](docs/PHASES.md#after-the-prototype).
