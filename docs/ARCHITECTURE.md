# Architecture

The Data Onboarding Agent is a **LangGraph state machine** with a **Gradio web UI** in front of it. Requesters describe the data they need in a chat. The agent fills a structured request, checks it against the code of the two platform repositories, [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion) and [data-onboarding-transformation](https://github.com/thanhphat2609/data-onboarding-transformation), to see what already exists and what has to be built, and hands it to the **Data Team** for approval. After approval it writes a User Story and posts a summary to Teams.

## System context

```mermaid
flowchart LR
    R([Requester]) -- chat --> UI
    DT([Data Team]) -- review tab --> UI
    subgraph App["Web app (app.py, Gradio)"]
        UI[Tabs: Request · Sessions · Data Team review · Settings · Debug]
        RUN[AgentRunner<br/>agent/runner.py]
        G[LangGraph graph<br/>agent/graph.py + agent/nodes/]
        UI --> RUN --> G
    end
    G -- read --> ING[(data-onboarding-ingestion<br/>templates · connections · jobs)]
    G -- read --> TRF[(data-onboarding-transformation<br/>dbt models)]
    G -- checkpoints --> DB[(SQLite<br/>checkpoints.db)]
    G -- files --> OUT[(outputs/&lt;request_id&gt;/)]
    G -. optional .-> LLM[Ollama LLM<br/>local or Colab tunnel]
    G -. optional .-> WEB[Public docs on the web<br/>sources the platform can't onboard yet]
    G -- webhook or mock file --> T[Teams channel]
```

## Components

| Component | Files | Role |
|---|---|---|
| Web UI | [app.py](../app.py) | Gradio app. Shows the chat, step tracker, request card and results. Holds the Data Team review queue. Also has settings for the LLM and the repositories the agent reads |
| Runner | [agent/runner.py](../agent/runner.py) | Thin API over the graph: `new_request`, `stream`, `reply`, `current_event`, `state`, `threads`. Used by the UI and the scripts |
| Graph | [agent/graph.py](../agent/graph.py) | Wires the nodes and routing functions; compiles with the SQLite checkpointer |
| Nodes | [agent/nodes/](../agent/nodes/) | One file per step (see [The graph](#the-graph)) |
| State | [agent/state.py](../agent/state.py) | `AgentState` TypedDict, the 7 required request fields, the questions for each field |
| Extraction | [agent/extraction.py](../agent/extraction.py) | Rule-based field extraction (English + Vietnamese keywords) and validation; LLM extraction when a model is configured |
| Repositories | [agent/repos.py](../agent/repos.py), [agent/github.py](../agent/github.py), [agent/dbt_project.py](../agent/dbt_project.py) | Read the two repos (local checkout or GitHub) into one cached `Knowledge`: source templates, connections, jobs, dbt models |
| Knowledge | [agent/knowledge.py](../agent/knowledge.py) | `lookup_source(system)`, `search_models(query)` (token-overlap score) over the repos |
| Web research | [agent/research.py](../agent/research.py) | For sources the platform can't onboard yet: find and read public docs, draft source notes, list questions for the Data Team |
| LLM client | [agent/llm.py](../agent/llm.py), [agent/prompts/](../agent/prompts/) | Optional Ollama client (API key support for the Colab proxy); prompts as Markdown files |
| Teams | [agent/integrations/teams.py](../agent/integrations/teams.py) | Adaptive Card to a Workflows webhook; without a URL (or on failure) writes `teams_messages.jsonl` |
| Config | [agent/config.py](../agent/config.py) | Paths and env vars, including which repos and branches to read |
| Infrastructure | [infrastructure/](../infrastructure/) | Dockerfile + compose for laptop, VM and Codespaces |

## The graph

```mermaid
flowchart TD
    START((start)) --> intake
    intake -- question pending --> ask_user
    ask_user -- "interrupt: wait for requester" --> intake
    intake -- complete, first time --> notify
    intake -- complete, already notified --> catalog_check
    notify --> catalog_check --> feasibility
    feasibility -- gap --> intake
    feasibility -- no gap --> investigate_source
    investigate_source --> approval
    approval -- "interrupt: wait for Data Team" --> approval
    approval -- request changes --> intake
    approval -- approve --> draft_us --> summary --> END((end))
```

| Node | File | What it does | Writes to state |
|---|---|---|---|
| `intake` | [intake.py](../agent/nodes/intake.py) | Extracts fields from new user messages, validates them (dates, ETA after today, refresh frequency) and decides what to ask next: missing fields (max 3 per turn) or a gap to resolve | `request`, `missing_fields`, `errors`, `gap`, `accepted_gaps`, `pending_question` |
| `ask_user` | [intake.py](../agent/nodes/intake.py) | `interrupt()`: pauses the graph until the requester answers | `messages` |
| `notify` | [notify.py](../agent/nodes/notify.py) | Once per request: writes `request.json`, posts "New data request" to Teams | `thread_ref` |
| `catalog_check` | [catalog_check.py](../agent/nodes/catalog_check.py) | Searches the dbt models of the transformation repo per source system | `existing_models` |
| `feasibility` | [feasibility.py](../agent/nodes/feasibility.py) | Per source and table: existing dbt model → landed by an ingestion job → system onboarded (new job) → supported source type (new connection) → otherwise a gap. Flags tight ETAs and snapshot history | `feasibility`, `gap` |
| `investigate_source` | [investigate.py](../agent/nodes/investigate.py) | Only for sources the platform can't onboard yet: web research and draft source notes (advisory) | `research` |
| `approval` | [approval.py](../agent/nodes/approval.py) | `interrupt()`: pauses until the Data Team approves or requests changes | `approved`, `review_comment` |
| `draft_us` | [draft_us.py](../agent/nodes/draft_us.py) | User Story from a fixed template (LLM only writes title/description); writes `feasibility.json`, `user_story.md` | `outputs` |
| `summary` | [summary.py](../agent/nodes/summary.py) | Writes `summary.md`, posts "Request approved — User Story ready" to Teams | `outputs` |

### Interrupts are the hand-off points

The graph stops in exactly two places, both with LangGraph's `interrupt()`:

- **`ask_user`**: waiting for the **requester**. The UI resumes it with `Command(resume=<answer text>)`.
- **`approval`**: waiting for the **Data Team**. The review tab resumes it with `Command(resume={"action": "approve" | "edit", "comment": ...})`.

`AgentRunner.current_event(thread_id)` turns the paused state into an event the UI renders: `question`, `approval`, `done` or `empty` (still running / not started).

## State

`AgentState` ([agent/state.py](../agent/state.py)), the most important keys:

| Key | Meaning |
|---|---|
| `request_id` | `REQ-<yyyymmdd>-<6 chars of thread_id>`; folder name in `outputs/` |
| `messages` | Chat history (append-only) |
| `request` | The 7 required fields: `dataset_description`, `sources`, `date_range`, `eta`, `refresh_frequency`, `grain`, `consumers` |
| `missing_fields`, `errors` | What is still missing or invalid |
| `gap`, `accepted_gaps` | Open feasibility gaps (`date_range`, `unknown_source`) and the ones the requester accepted |
| `existing_models`, `feasibility` | dbt model matches and the per-source assessment with recommendation and risks |
| `research` | Web research findings per source the platform can't onboard yet |
| `approved`, `review_comment` | The Data Team's decision |
| `outputs` | Paths of the generated files and the User Story title |

One chat session = one LangGraph `thread_id`. Every step is checkpointed in SQLite, so a session survives restarts and can be reopened from the **Sessions** tab.

## Design rules

1. **Decisions live in code; the LLM only helps with language.** Routing, validation and feasibility are deterministic Python. The LLM (if configured) extracts free-text fields, rephrases questions and writes the User Story title and description. If it is missing or fails, the rule-based path takes over (`safe_call`).
2. **Never guess platform facts.** What is onboarded, landing or modelled comes only from the two repos; every recommendation cites the file it came from.
3. **Web research is advisory.** Findings for unknown sources go into the User Story and the questions for the Data Team. They never change the feasibility result: the source stays *Needs investigation* until the ingestion repo can onboard it.
4. **A human approves.** Nothing is drafted until the Data Team approves. A requested change sends the request back through intake and feasibility.
5. **No sample data.** The agent only knows what the two repos contain. If a repo can't be read, the header pill turns red and every feasibility result carries the error as a risk.
6. **External calls must not break the flow.** A failing Teams webhook or web page is logged to a file and the flow continues.

## Knowledge

| Repo | Files | Used for |
|---|---|---|
| data-onboarding-ingestion | `code/templates/sources/*.yaml` | Source types that can be onboarded (`new_connection`) |
| | `pipelines/connections/*.yaml` | Systems already onboarded (`new_job`); system = system of its jobs, else the first part of the name (`crm-sqlserver-nonprod` → `crm`) |
| | `pipelines/jobs/*.yaml` | Tables landing in the lake, from `sink.params.path` = `<system>/<schema>/<table>` (`landed`) |
| data-onboarding-transformation | `models/**/*.yml`, or `target/manifest.json` if committed | dbt models (`existing_model`); system from `meta.source`, `stg_<system>__…` or the folder `models/<layer>/<system>/` |
| this repo | `doc_links.yaml` | `investigate_source`: official docs to read first |

Each repo is read from a local checkout (`INGESTION_PATH`, `TRANSFORMATION_PATH`) or from GitHub (`*_REPO`, `*_REF`, `GITHUB_TOKEN`), once per process; **⚙️ Settings → Reload repositories** reads them again.

Feasibility has no history dates to compare: ingestion keeps one snapshot per day from its first run (ingestion ADR-0004), so the agent adds a history risk instead of a date-range gap. Lead times per kind of work are rough team estimates in `LEAD_TIME_DAYS` ([feasibility.py](../agent/nodes/feasibility.py)).

## Storage

| What | Where | Notes |
|---|---|---|
| Sessions (checkpoints) | `CHECKPOINT_DB`, default `./checkpoints.db`; `outputs/checkpoints.db` in Docker | SQLite. PLAN: Postgres after the prototype |
| Per-request files | `outputs/<request_id>/` | `request.json`, `feasibility.json`, `user_story.md`, `summary.md`, `teams_messages.jsonl`, `source_notes_<source>.yaml` |
| Evaluation runs | `outputs/eval/<timestamp>/` | `report.md`, `mistakes.csv` from `scripts/run_samples.py` |

## Web UI

The UI keeps no state of its own beyond the current `thread_id`: every panel is re-rendered from the graph state (`_view` in [app.py](../app.py)).

| Tab | For | What it does |
|---|---|---|
| 💬 Request | Requester | Chat with example prompts. A step tracker (Describe → Details → Feasibility → Review → User Story), a live "Your request" card, a read-only "Waiting for Data Team review" panel, and the finished User Story with downloads |
| 🗂 Sessions | Anyone | Reopen a recent session (from the checkpointer) or one pasted by `thread_id` |
| 🛡 Data Team review | Data Team | Queue of requests waiting for approval; request card + feasibility; **Approve** / **Request changes**. Behind `REVIEWER_KEY` if set |
| ⚙️ Settings | Admin | LLM host/model/API key at runtime; what was read from the two repos, reload |
| 🔧 Debug | Developer | Raw state JSON |

While a request waits for review, the Request tab polls every 5 seconds (`gr.Timer`). It compares a fingerprint of the thread (message count + event type) and re-renders when the Data Team's decision lands.

> `REVIEWER_KEY` is a soft gate, not authentication: the app has no logins. Keep the port private (see [infrastructure/README.md](../infrastructure/README.md)).

## Deployment

| Where | How | Model |
|---|---|---|
| Laptop (venv) | `python app.py` | Rule-based, local Ollama, or Colab via tunnel |
| Docker (laptop / VM) | `docker compose -f infrastructure/compose.yaml up -d --build` | Same; host Ollama via `host.docker.internal` |
| GitHub Codespaces | Same compose command (Docker is preinstalled) | Colab via tunnel |
| Colab only | Notebook option B: app with `share=True` on Colab | Ollama on the Colab GPU |

The Colab-hosted model sits behind [scripts/ollama_auth_proxy.py](../scripts/ollama_auth_proxy.py) (API key, read/chat endpoints only) and a cloudflared tunnel. See the main [README](../README.md#deployment-model-on-colab-web-app-on-your-machine).

## Extension points

| To… | Change |
|---|---|
| Support a new source | In data-onboarding-ingestion: a source template (new type), a connection (new system) or a job (new table); the agent picks it up on reload |
| Add a required field | `REQUIRED_FIELDS` / `FIELD_QUESTIONS` in `state.py`, extraction + validation in `extraction.py`, `FIELD_NAMES` in `app.py`, the User Story template |
| Add a step | New node in `agent/nodes/`, wire it in `graph.py`, add it to `NODE_STATUS` / `NODE_STEP` in `app.py` |
| Swap the checkpointer | `get_checkpointer` in `graph.py` (e.g. Postgres); `AgentRunner.threads` reads the SQLite table directly |
| Create real tickets | After `draft_us`: a node that calls Azure DevOps / Jira (out of scope for the prototype) |
