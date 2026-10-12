# Data Onboarding Agent – Prototype Plan

## Overview

**Repo:** `data-onboarding-agent`

**Description:**
> An AI agent that turns data requests into ready-to-build work: it gathers requirements from users step by step, checks existing data and source feasibility (availability, date range, ETA), notifies the data team on Teams, and drafts user stories with a pipeline proposal — with human approval at every key step.

**Prototype goal:** prove the agent can do 3 things:
1. Ask the right questions and collect complete information from users
2. Assess feasibility correctly: does the data already exist, which source to use, what date range is obtainable
3. Produce a User Story the Data Team can actually use

All external systems (Teams, Snowflake, Azure DevOps/Jira) are **mocked** at this stage; real connections come later.

---

## Stack

| Component | Choice | Notes |
|---|---|---|
| Environment | Google Colab | Prototype only |
| LLM | Ollama + a 7B–14B model (e.g. Qwen2.5) | Fits a T4 GPU |
| Orchestration | LangGraph | Nodes, branching, interrupt for approval |
| State | `SqliteSaver` → `.db` file on Google Drive | Survives Colab disconnects |
| UI | Gradio (`share=True`) | Temporary link for demos |
| Knowledge | YAML playbooks + dbt catalog (exported from the manifest) | Written by the team |
| Output | JSON + Markdown files in `outputs/` | Separate from checkpoints |

---

## Flow

```
[intake] ──all fields──▶ [notify] ──▶ [catalog_check] ──▶ [feasibility]
   ▲                                                         │
   └──────────── gap (date range, source) ◀──────────────────┤
                                                             │ no gap
                                                             ▼
                                          [approval] (interrupt, wait for reviewer)
                                                             │
                                                             ▼
                                          [draft_us] ──▶ [summary] ──▶ END
```

| Node | What it does | Input → Output |
|---|---|---|
| `intake` | Ask the user until all required fields are filled | Chat → `request` (JSON) |
| `notify` | Tell the Data Team about the new request (mock: print/write file) | `request` → `thread_ref` |
| `catalog_check` | Search the dbt catalog for data that already exists | `request` → `existing_models` |
| `feasibility` | Look up playbooks, compare date ranges, propose how to get the data | → `feasibility`, `gap` |
| `approval` | Pause for approve / edit | → `approved` |
| `draft_us` | Generate the User Story + pipeline proposal | → `user_story.md` |
| `summary` | Final summary posted back to the same thread | → `summary.md` |

### Request schema (required fields)
- `dataset_description` – what data is needed and what it is for
- `sources` – sources (GA4, GSC, AppsFlyer, CM, GAM, DV360, DataForSEO, other)
- `date_range` – from date → to date
- `eta` – date the data must go live
- `refresh_frequency` – daily / hourly / one-off
- `grain` – level of detail (day, campaign, user…)
- `consumers` – who uses it and where (dashboard, report…)

---

## Repo structure

```
data-onboarding-agent/
├── notebooks/
│   └── prototype.ipynb        # Colab setup, run Ollama + Gradio
├── agent/
│   ├── state.py               # TypedDict state
│   ├── graph.py               # build graph, checkpointer
│   ├── nodes/                 # one file per node
│   └── prompts/               # prompts per node (.md)
├── playbooks/                 # one YAML file per source
│   ├── ga4.yaml
│   ├── gsc.yaml
│   └── ...
├── catalog/
│   └── dbt_models.json        # exported from the manifest
├── outputs/                   # request JSON, user_story.md, summary.md
├── tests/
│   └── sample_requests/       # real past requests for test runs
└── README.md
```

### Sample playbook
```yaml
source: ga4
access_methods:
  - type: bigquery_export
    available_from: "<BQ link date>"   # no backfill before this date
  - type: data_api
    notes: "quota limits, sampling"
current_connector: "<connector the team uses>"
existing_models: [stg_ga4__events]
owner: "<owner>"
notes: ""
```
> Fill in retention / limits from official docs and the team's real experience. Never let the agent guess.

---

## Phases

### Phase 0 – Setup (1–2 days)
- [ ] Create the repo and folder structure above
- [ ] Notebook: mount Drive, install Ollama, pull a model, test chat
- [ ] Test the model calling simple tools (1–2 fake tools)
- [ ] Pick a model: try 7B and 14B, compare tool-calling stability

### Phase 1 – Intake (3–4 days)
- [ ] Define `state.py` + request schema
- [ ] `intake` node: ask for missing fields, validate (valid dates, ETA after today…)
- [ ] Gradio chat wired to the graph, one session = one `thread_id`
- [ ] `SqliteSaver` checkpointer on Drive, test restarting Colab and continuing

### Phase 2 – Knowledge (2–3 days)
- [ ] Write playbooks for 7 sources: GA4, GSC, AppsFlyer, CM, GAM, DV360, DataForSEO
- [ ] Export dbt models + descriptions from `manifest.json` → `catalog/dbt_models.json`
- [ ] Tools `lookup_playbook(source)` and `search_catalog(query)`

### Phase 3 – Feasibility (3–4 days)
- [ ] `catalog_check` node: is the data already in some model
- [ ] `feasibility` node: compare the requested date range with the obtainable one
- [ ] Branch on gaps → back to `intake` to ask the user to accept an alternative
- [ ] Propose how to get the data: existing model / API / ingestion from BQ

### Phase 4 – Approval + Output (2–3 days)
- [ ] `interrupt_before=["approval"]`, UI with Approve / Edit buttons
- [ ] `draft_us` node: User Story from a template (title, description, acceptance criteria, sources, proposed pipeline, risks)
- [ ] `summary` node: final summary message
- [ ] Write outputs to `outputs/<request_id>/`

### Phase 5 – Teams + Demo (2 days)
- [ ] Post to a channel via a Teams Workflows webhook (notify + summary)
- [ ] Run 3–5 real past requests from `tests/sample_requests/`
- [ ] Compare agent output with how the team actually handled them, log the mistakes
- [ ] Demo to the team

**Total:** ~3 weeks part-time.

> Actual status of each item: see README.md.

---

## Success criteria
- The agent collects all required fields in ≤ 5 turns for a normal request
- Correctly detects date range gaps in test requests that have them
- Correctly recognizes when the data already exists in the catalog
- The Data Team rates the User Story "usable, needs only minor edits"

## Out of scope for the prototype
- Creating real User Stories in Azure DevOps/Jira
- Approving inside Teams (needs a bot / Graph API)
- Real Snowflake connection
- Generating pipeline code
- Deploying to a VM, auth, concurrent users

## Risks
| Risk | Mitigation |
|---|---|
| Small models call tools unreliably | Try 14B; keep branching logic in code, the LLM only fills in / phrases |
| Playbooks missing or wrong | Team reviews playbooks before testing; the agent always cites its sources |
| Colab disconnects / runs out of GPU | Checkpoints on Drive; the prototype doesn't need to run continuously |
| Sensitive data on Colab | The prototype uses only metadata + sample requests, no real data |

## After the prototype
1. Move to a VM (Docker), checkpointer → Postgres
2. Model: Ollama/vLLM on a GPU VM, or an LLM API approved by the company
3. Teams bot to approve directly in the thread
4. Create real User Stories in Azure DevOps/Jira
5. Read Snowflake metadata directly instead of a manually exported catalog
