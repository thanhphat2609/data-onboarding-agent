# Phases

Status of each phase of the prototype plan ([PLAN.md](../PLAN.md)) plus the work added after it.

> Updated: 2026-10-26. ✅ done and verified · 🟡 code exists, not yet run/verified in the real environment · ⬜ not started

## Overview

| Phase | Goal | Status |
|---|---|---|
| 0 – Setup | Repo, Colab notebook, model choice | 🟡 Notebook written, not run on Colab; model not picked |
| 1 – Intake | Collect the 7 details in a chat, persist sessions | ✅ |
| 2 – Knowledge | What exists and what can be onboarded | ✅ Read from the real ingestion and transformation repos (replaced playbooks + catalog on 2026-10-23) |
| 3 – Feasibility | Existing data, what has to be built | ✅ dbt model → landed table → new job → new connection → gap |
| 4 – Approval + Output | Data Team approval, User Story, summary | ✅ |
| 5 – Teams + Demo | Teams webhook, real past requests, demo | 🟡 Mock works; real webhook, real requests and demo pending |
| Added: Web research | Investigate sources the platform can't onboard yet | ✅ |
| Added: Infrastructure | Docker / Codespaces | 🟡 Written, not yet built in real Docker |
| Added: UI redesign + Data Team review | Friendlier UI; approval by the Data Team only | ✅ Tested locally in a browser |
| Added: Knowledge from the platform repos | No sample data; the agent reads the two repos | ✅ 5/5 scenarios against the real repos |
| Added: Web search port + code layout | Python port of web-search-mcp (module + MCP server); `agent/` in functional folders | ✅ Tested live (search, pages, research, MCP over stdio) |
| Added: CI/CD | Checks on every push; deploy to VM 1 when someone runs the Deploy workflow | 🟡 CI written (runs on GitHub); deploy waits for VM 1 |

---

## Phase 0 – Setup
- ✅ Repo + folder structure
- 🟡 Notebook [notebooks/prototype.ipynb](../notebooks/prototype.ipynb): clone the private repo (token from Colab Secrets), install Ollama, pull models, test chat. **Written, not yet run on Colab**
- 🟡 Tool-calling test (`lookup_source`, `search_models`): the cell is in the notebook, not yet run
- ⬜ Pick 7B vs 14B: run the comparison cell on a Colab T4

## Phase 1 – Intake ✅
- ✅ `state.py` + request schema (7 required fields)
- ✅ `intake` node: asks for missing fields (max 3 per turn), validates the date range, ETA after today, valid refresh frequency
- ✅ Gradio web UI ([app.py](../app.py)), one session = one `thread_id` (redesigned later, see [UI redesign](#added-ui-redesign--data-team-review-2026-10-23))
- ✅ `SqliteSaver` checkpointer; "restart and continue" tested locally (new runner on the same `.db` file). 🟡 Not yet tested with a `.db` file on Google Drive

## Phase 2 – Knowledge ✅
- ✅ *Since 2026-10-23:* the agent reads the code of the two platform repos ([agent/repos/__init__.py](../agent/repos/__init__.py)) from a local checkout or GitHub (`GITHUB_TOKEN`):
  - [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion): source templates, connections, jobs
  - [data-onboarding-transformation](https://github.com/thanhphat2609/data-onboarding-transformation): dbt models
- ✅ Tools `lookup_source(system)` and `search_models(query)` ([agent/repos/lookup.py](../agent/repos/lookup.py))
- *Replaced:* YAML playbooks per source (`playbooks/`, demo GA4/AppsFlyer playbooks) and a synced dbt catalog (`catalog/`, Settings → dbt catalog, `scripts/export_dbt_catalog.py`)

## Phase 3 – Feasibility ✅
- ✅ `catalog_check` node: finds related dbt models per source system in the transformation repo
- ✅ `feasibility` node, per source and table: existing dbt model → landed by an ingestion job (needs dbt models) → system onboarded (new job) → supported source type (new connection) → gap. Warns about tight ETAs (`LEAD_TIME_DAYS`) and snapshot history
- ✅ Gap (source the platform can't onboard) → back to `intake` to ask the user to accept or pick an alternative
- *Replaced:* date-range gaps from playbook `available_from` / `max_lookback_days`; the repos hold no history dates, so this is a risk note now

## Phase 4 – Approval + Output ✅
- ✅ Approval pauses for the **Data Team** (`interrupt()` inside the node; equivalent to `interrupt_before=["approval"]`, but receives the decision payload on resume). Since 2026-10-23 the decision is made in the **🛡 Data Team review** tab, not by the requester. Request changes → back to intake to update the request → feasibility re-checked
- ✅ `draft_us` node: User Story from a template (title, user story, description, sources & feasibility, proposed pipeline, acceptance criteria, risks, information sources)
- ✅ `summary` node: final summary message
- ✅ Outputs written to `outputs/<request_id>/`: `request.json`, `feasibility.json`, `user_story.md`, `summary.md`

## Phase 5 – Teams + Demo
- 🟡 Teams Workflows webhook (notify + summary, Adaptive Card): code exists, **not tested with a real webhook**. Check a URL with `python -m agent.integrations.teams "<url>"`. Without `TEAMS_WEBHOOK_URL` it mocks by writing `outputs/<request_id>/teams_messages.jsonl`. If the webhook call fails, the flow continues and the message goes to the same file with `webhook_error`
- 🟡 Replay tool for past requests: `python -m agent.workflow.evaluate <folder>` ([evaluate.py](../agent/workflow/evaluate.py)). The 5 scripted scenarios used during development (2026-10-23) were removed from the repo. ⬜ Add 3–5 real past requests
- ✅ Comparison tooling: a `team_handling` block in a sample (how the team actually handled it) is compared with the agent's result. Every run writes `outputs/eval/<timestamp>/report.md` (with a reviewer rating column) and `mistakes.csv` (one row per difference, with a `reviewer_notes` column). ⬜ Run it on real requests and review
- 🟡 Demo runbook: [DEMO.md](../DEMO.md). ⬜ Demo to the team

---

## Added: Web research for sources the platform can't onboard yet ✅ (2026-10-20)
When the platform can't onboard a source and the requester replies `ok`, the `investigate_source` step (after feasibility, before approval) looks up the source's public docs:
1. **Finds pages**: links the requester pasted in the chat → a DuckDuckGo search (`ddgs`, no API key) for the remaining slots (max 3 pages).
2. **Reads them** with plain HTTP and keeps sentences about data history/retention, quotas, auth and access methods. Pages that need JavaScript to render can't be read; they are listed as such.
3. **Writes**: a *Web research (unverified)* section and a *Questions for the Data Team* section in the User Story, the questions in the Teams summary card, a short note in the review panel, and draft source notes `outputs/<request_id>/source_notes_<source>.yaml` (renamed from the draft playbook on 2026-10-23). With an LLM it also summarises and fills access methods in the draft; without one you get the key passages + standard questions.

The findings **never change the feasibility result** (the source stays "Needs investigation"). Only the source name + fixed keywords are sent to the search engine, never the request text. Turn it off with `WEB_RESEARCH=0`; `agent/workflow/evaluate.py` keeps it off unless you pass `--web`.
To make the source known: add a source template, connection or job for it in data-onboarding-ingestion; the agent picks it up on reload.

- 🟡 2026-10-25: **research in rounds** (it was too quick: 2 fixed queries, 3 pages, first sentences only). Now: one search per topic + official docs, docs site ranked first, best sentences per page (numbers first), follow-up `site:` searches for topics without evidence, up to 8 pages / 2 rounds / 180 s per source, every query listed in the User Story ([ARCHITECTURE.md](ARCHITECTURE.md#web-search)). Same day: the source name is an exact phrase in every query and off-topic results (not naming the source) are dropped, after real searches drifted to other products. Round logic checked offline with a fake search engine; ⬜ check with real searches in a codespace
- 🟡 2026-10-26: **top 5 links per source** in the User Story, review panel and Teams summary, read or not, with the topics each was found for; a ready-made search link when nothing was found. Before, links found but not read (fetch failed, no useful sentences) were lost. Checked offline with a fake search engine; ⬜ check in a codespace
- 🟡 2026-10-26: **Web research fix: the source name, not the engine.** The last Google Search Console request searched for `"product called: google search console"`: the requester's lead-in stayed in the source name, and as an exact phrase it matched nothing (`0 / 0`) or every result was dropped as off-topic (`0 / 7`). Fixed: lead-ins (`product called:`, `dataset called`, `tool named`, `tên là`…) are dropped from source names; queries use the plain name, no quotes; when every result is off-topic the note says "check the source name" instead of blaming rate limits. Web search cut down to two tools, `web_search` and `web_fetch` (module and MCP server); over 10 searches a minute now waits instead of failing. New question, asked on its own after a source the platform can't onboard: **"Where does it come from?"** (vendor/app, API/database/file, docs link), shown in the User Story; a pasted link is read first and a known vendor is added to the search name. Checked offline end to end with a fake search engine; ⬜ check with real searches in a codespace
- 🟡 2026-10-26: **SearXNG + Trafilatura, still no API key.** A self-hosted SearXNG container is the first search engine (several engines per query, against the `(0 / 0)` rate-limit results); the Bing/Brave/DuckDuckGo scrapers are the fallback. Trafilatura extracts page text, the old rules are the fallback (on the Search Console limits page: 17 passages instead of 14). API-based search (Tavily, Brave API…) left out on purpose. Client checked against a fake SearXNG; ⬜ check the container in a codespace

## Added: Infrastructure 🟡 (2026-10-23)
- ✅ [infrastructure/](../infrastructure/): `Dockerfile` (Python 3.12 slim, non-root, healthcheck), `compose.yaml` (localhost-only port, settings from env / `.env`, `outputs/` bind-mounted), `.env.example`, README with how to open the UI
- ✅ Same command on a laptop, a VM and GitHub Codespaces (Docker is preinstalled there)
- ✅ `app.py --host`; `GITHUB_TOKEN` to read the two repos (in Codespaces, export your own: the preset one only reads the codespace's repo)
- ⬜ Build and run the image in real Docker / a codespace (no Docker was available when it was written)
- 🟡 2026-10-24: `compose.yaml` → `docker-compose.yml` like the other repos; two-stage Dockerfile (venv built separately, pip cache mount, only `agent/` + `app.py` copied); healthcheck, `init`, log rotation and `container_name` in compose

## Added: Login with roles 🟡 (2026-10-24)
> Code done and the login/role rules unit-checked; not yet clicked through in a browser (test in Codespaces).
- 🟡 Login page when `ACCOUNTS` / `ACCOUNTS_FILE` is set (`user:password`, from env or a secret, never in the repo); no accounts = no login (local development)
- 🟡 `DATA_TEAM` accounts (default `data.team@gmail.com`) see every tab and every session; replaces `REVIEWER_KEY`
- 🟡 Other accounts are requesters: only **Request** and **Sessions**, and only their own sessions (`requested_by` stored with each request)
- 🟡 Review and Settings handlers check the role on the server too; "Signed in as … · Log out" bar
- 🟡 2026-10-24: requesters self-register. Only the Data Team needs `ACCOUNTS`; any other email's first sign-in sets its password (scrypt hash in the `requesters` table), and a `DATA_TEAM` email can't self-register. Rules checked with an in-memory store; not yet in the browser

## Added: PostgreSQL + sessions table 🟡 (2026-10-24)
> Code done; the SQLite path ran end to end locally (ownership and on-behalf rows checked). PostgreSQL and the compose stack are not yet run: test in Codespaces.
- 🟡 `postgres` service (PostgreSQL 16.15) in [docker-compose.yml](../infrastructure/non-prod/docker-compose.yml): the platform's one server, databases `onboarding_agent` (this app), `airflow` (Airflow metadata) and `platform` (ingestion run records), one role each, created by [postgres/init/01-databases.sh](../infrastructure/postgres/init/01-databases.sh); shared Docker network `data-platform` for Airflow
- 🟡 `DATABASE_URL` → `PostgresSaver` on a psycopg pool; without it SQLite as before (laptop, Colab)
- 🟡 `sessions` table ([sessions.py](../agent/workflow/sessions.py)) in the same database: Sessions list, review queue and ownership checks are SQL instead of loading every thread; existing sessions are backfilled on start
- 🟡 `requested_by` (owner) vs `created_by` (who typed it) vs `reviewed_by`: the Data Team can file a request **on behalf of** a requester
- ❌ DNS fix with `DNS_1` / `DNS_2` (default 1.1.1.1 / 8.8.8.8), v0.6.0: public resolvers don't answer from a Codespace's Docker. Removed in v0.6.1 (Docker's default DNS again)
- ✅ Root cause of "DNS lookup of api.github.com failed" and the PostgreSQL `PoolTimeout` in Codespaces, found 2026-10-24: a leftover `iptables-legacy` rule `-P FORWARD DROP` that only lets `docker0` through, so the compose network can reach neither `postgres` nor the internet. Not a code problem. Every new codespace starts with it (seen again 2026-10-25), so `.devcontainer/devcontainer.json` runs `infrastructure/non-prod/codespace-network.sh` (`iptables-legacy -P FORWARD ACCEPT`) on each start ([runbook](../infrastructure/README.md#codespaces-containers-cant-reach-each-other-or-the-internet)); then the app reached PostgreSQL and GitHub
- 🟡 v0.6.1: compose moved to `infrastructure/non-prod/` (same layout as data-onboarding-ingestion; `prod/` once VM 1 exists); `PLATFORM_GITHUB_TOKEN` wins over `GITHUB_TOKEN`, because the Codespaces preset token gave 404 on both repos
- ⬜ Run in a codespace: `up -d --build`, a full request + approval, then the queries in [POSTGRESQL.md](POSTGRESQL.md)

## Added: UI redesign + Data Team review ✅ (2026-10-23)
- ✅ Tabs: **💬 Request**, **🗂 Sessions**, **🛡 Data Team review**, **⚙️ Settings**, **🔧 Debug**; admin tools are out of the requester's way
- ✅ Request tab: welcome screen with example prompts, step tracker (Describe → Details → Feasibility → Review → User Story, amber on gaps), live "Your request" card (x/7 details), status pills, User Story preview + download
- ✅ Approval by the Data Team only: review queue, request card + feasibility, Approve / Request changes; optional `REVIEWER_KEY`. The requester sees "Waiting for Data Team review" and their page updates on its own (5 s poll)
- ✅ Sessions tab lists recent sessions from the checkpointer
- ✅ Theme (Inter, indigo/slate), dark mode, phone width
- ✅ Verified in a headless browser: full request flow, request changes → requester sees the update → approve → downloads; unknown-source gap; Sessions reopen; reviewer key gate

---

## Added: Knowledge from the platform repos ✅ (2026-10-23)
- ✅ No sample data left in this repo: removed `demo/`, `playbooks/`, `catalog/`, `sample_requests/_template.yaml` and `scripts/export_dbt_catalog.py`
- ✅ [agent/repos/__init__.py](../agent/repos/__init__.py) reads data-onboarding-ingestion (templates, connections, jobs) and data-onboarding-transformation (dbt models) into one cached `Knowledge`; **⚙️ Settings → Repositories** shows what was read and reloads it
- ✅ Sources are systems of the ingestion repo (e.g. `crm`), or a new system named with its type ("ERP on PostgreSQL")
- ✅ Feasibility per table, User Story pipeline steps that name the files to add in each repo, UI labels per kind of work
- ✅ `GITHUB_TOKEN` (fine-grained, read-only on both repos) replaces `DBT_GITHUB_TOKEN`
- ✅ Scenarios rewritten against the real repos (5/5 passed; later removed from the repo, see Phase 5)

## Added: Web search port + code layout ✅ (2026-10-23)
- ✅ [agent/research/websearch/](../agent/research/websearch/): Python port of [web-search-mcp](https://github.com/mrkrsl/web-search-mcp) (MIT, license kept next to the code). Search without API keys (Bing → Brave → DuckDuckGo with the original's quality check, plus the `ddgs` package as last fallback), page content over HTTP with a headless-Chromium fallback, concurrent fetching
- ✅ MCP server with the original's three tools: `python -m agent.research.websearch.mcp_server` (tested over stdio with an MCP client). *Since 2026-10-26:* two tools, `web_search` and `web_fetch`
- ✅ Web research ([investigate.py](../agent/research/investigate.py)) uses it instead of `ddgs` + a plain HTML parser, so JavaScript-only docs pages can be read when the browser is installed
- ✅ The headless browser is optional: Playwright is in `requirements.txt`, but Chromium is only downloaded on request (`python -m playwright install chromium`, Docker `WITH_BROWSER=true`); without it everything runs over HTTP
- ✅ Not ported on purpose: fingerprint spoofing / simulated mouse movement; two cleanup bugs fixed (see [ARCHITECTURE.md](ARCHITECTURE.md#web-search))
- ✅ Removed `doc_links.yaml` (team-kept doc links per source): research now uses the links the requester pastes plus web search
- ✅ `agent/` reorganised into `workflow/`, `repos/`, `research/`, `llm/`, `integrations/` (5/5 scenarios passed after the move); `scripts/` dissolved: replay → `agent/workflow/evaluate.py`, Ollama proxy → `notebooks/`, Teams test → `python -m agent.integrations.teams <url>`
- ⬜ Build the Docker image with `WITH_BROWSER=true`

## Known issues / backlog
- ✅ *Fixed 2026-10-25.* **A vague source was researched as is.** "google (maybe bigquery or api from google)" became the source, and web research searched for Google in general (pages about Google's real estate). Now guesses in parentheses are dropped (`google (search console)` keeps the product), and a company name alone (Google, Microsoft, Amazon/AWS, Meta/Facebook, Adobe, Oracle, SAP) gets a question asking which product, with examples ([extraction.py](../agent/workflow/extraction.py)).
- ✅ *Fixed 2026-10-23.* **A message typed while waiting for the Data Team was always treated as a change** (a question like "any idea about Google Search Console data" re-ran the check and repeated the same reply). Now ([followup.py](../agent/workflow/followup.py)): questions are answered from the two repos (what ingestion/transformation have for that source, what exists today as examples) and nothing changes; **add** adds the source; changes are shown first and applied only after **yes**. Tested by replaying messages; not yet clicked through in the browser.
- ✅ *Fixed 2026-10-23.* **A failed repo load stuck until Reload, with an unclear error.** Seen in a codespace: `NameResolutionError` for api.github.com (container networking, not the token; root cause found 2026-10-24: the Codespaces legacy firewall rule, see Phase "PostgreSQL + sessions table"). GitHub calls now retry transient network errors, the error says it is a network/DNS problem, and a failed load is retried after 60 s. Diagnosis steps: [infrastructure/README.md](../infrastructure/README.md#troubleshooting).
- ✅ *Fixed 2026-10-23.* **ETA ranges were not understood.** "ETA must be in 2 or 3 weeks" made the agent ask again. Ranges ("2 or 3 weeks", "2-3 weeks", "2 đến 3 tuần") now take the earlier date, and a bare "2 weeks" works as an ETA answer. The "Noted: go-live date" confirmation now also shows when the same answer contains other dates. Free-text sources drop label/hedge words ("Source maybe from Google BigQuery" → `google big query`, type `bigquery`).
- **Key-less web search is fragile.** Engines can rate-limit or bot-check a network: in testing, Bing gave generic results even in the headless browser, html.duckduckgo.com answered with a challenge, and `ddgs` stopped returning results after many test queries. Brave in the headless browser was the reliable engine. Research then reports "web search found nothing" and still asks its standard questions. (The `0 / 0` and `0 / 7` searches seen on 2026-10-26 were a bad source name, not rate limiting; see the web research fix.) Since 2026-10-26 a self-hosted SearXNG asks several engines per query, which should make this rarer; it scrapes from the same network, so it doesn't remove it. API-based search is left out on purpose (no keys).
- ✅ *Fixed 2026-10-23.* **Relative ETAs were not understood.** "Go live should be next two weeks" made the agent repeat the ETA question with no explanation. It now reads relative dates in English and Vietnamese ("in 2 weeks", "end of next month", "2 tuần nữa", "cuối tháng") and confirms the date it computed ("Noted: go-live date 2026-11-06"). When nothing in an answer matches the questions, it says so instead of silently asking again.
- **"ok" can be taken as a field answer.** If a field is still pending (e.g. "Used by"), replying `ok` stores "ok" as its value. Seen 2026-10-23. Fix idea: ignore yes-words as values for free-text fields.
- **The Data Team can't ask the requester a question.** "Request changes" applies the comment as an edit to the request. A "send back with a question" action would need a new branch from `approval` to `ask_user`.
- **The reviewer key is a soft gate**, not authentication; the app has no logins. Real auth (SSO in front of the app, or a Teams bot for approvals) is post-prototype.
- **Chat doesn't auto-scroll** when the Data Team's decision arrives while the Request tab is in the background. Scroll down once.
- ✅ *Fixed 2026-10-20 by web research.* **Source without a playbook: "ok" did not trigger any investigation** (reported 2026-10-12, seen with GSC). Replying `ok` only recorded the risk and moved on, while the message read as if the agent would investigate. Reworded, and the `investigate_source` step was added. (Playbooks were replaced by the ingestion repo on 2026-10-23; a source is known once that repo can onboard it.)

## Added: CI/CD 🟡 (2026-10-26)
Same two stages as data-onboarding-ingestion ([its ADR-0012](https://github.com/thanhphat2609/data-onboarding-ingestion/blob/main/docs/adr/0012-cicd-ssh-deploy.md)); setup in [infrastructure/prod/README.md](../infrastructure/prod/README.md).
- 🟡 [ci.yml](../.github/workflows/ci.yml) on every pull request and push to `main`: ruff (runtime errors only), compile, `import app`, Compose files valid, image builds. Checked locally: ruff and `import app` pass
- 🟡 [deploy.yml](../.github/workflows/deploy.yml) run by hand (Actions → Run workflow, the approval), only for a commit on `main` with green CI: over SSH on VM 1 `git checkout <sha>`, `docker compose build --pull`, `up -d --wait`, prune old images and build cache. Off until the variable `PROD_DEPLOY_ENABLED` is `true`
- 🟡 [infrastructure/prod/](../infrastructure/prod/): compose for VM 1 (postgres + app, required passwords, creates `data-platform`), `.env.example`, `deploy.sh`
- ⬜ When VM 1 exists: GitHub secrets and variables from the prod README, then the first deploy (this repo before data-onboarding-ingestion)

## Next phase: 3 User Stories per request
> ⬜ Planned 2026-10-26, not started. Today one User Story is drafted after approval.

The two platform repos are separate (ingestion lands the data, transformation models it), so after the Data Team approves, the agent drafts **3 User Stories** instead of one, linked to each other:

| # | User Story | Repo | Content | Done when |
|---|---|---|---|---|
| 1 | **Spike: the dataset** | none (investigation) | Source: what it is, where it comes from, access method, auth, owner. Freshness: how often the source updates, delay, how far back history goes. Strengths: what it does well for this request. Weaknesses: quotas, sampling, missing fields, history limits, risks. Starts from the web research, the requester's "where does it come from?" answer and the draft source notes | The team has a go/no-go and an access route; source notes checked |
| 2 | **Ingestion** | data-onboarding-ingestion | Source template / connection / job to add (from feasibility), landing table, schedule matching the refresh, backfill from the start date | Raw data lands on schedule from the start date |
| 3 | **Transformation** | data-onboarding-transformation | dbt models at the requested grain, tests, freshness test, hand-over to the consumers | Model reconciles with the source UI, live by the ETA |

Order: 1 → 2 → 3 (each blocked by the previous one). Open points: whether a source the platform already ingests still gets a spike (or a short one), and whether US 2 is skipped when the data already lands (feasibility `landed` / `existing_model`).

## Next steps

> **Where we left off (2026-10-26).** v0.8.0 is tagged and pushed: research in rounds, the source name as an exact phrase, "which product?" for a company name, top 5 links per source, SearXNG as the first search engine and Trafilatura for page text (no API keys). Only checked offline; the `searxng` container has not run yet.
> **To pick up:** (1) after any `git pull`, run `docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build`, because the code lives in the image; (2) with a **new** request for a source the platform lacks (e.g. Google Search Console), check the User Story's *Web research* section: top links, searches, kept/off-topic counts, docs site, passages; (3) if engines rate-limit (searches with `(0 / 0)`), check the `searxng` container's logs (`docker compose -f infrastructure/non-prod/docker-compose.yml logs searxng`).
> 2026-10-26: CI runs on every push (green); the Deploy workflow is ready, run by hand as the approval, off until VM 1 exists ([infrastructure/prod/README.md](../infrastructure/prod/README.md)). data-onboarding-ingestion committed its ADR-0011 and expects this stack to host the shared PostgreSQL server; on VM 1 deploy this repo first.

1. Run the notebook on Colab: tool-calling test, pick a model, host the model for the web app.
2. Build and run the Docker image (`docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build`), locally or in a codespace, with `PLATFORM_GITHUB_TOKEN` set (Codespaces secret).
3. As the platform grows (more templates, connections, jobs, dbt models), replay a few requests with `python -m agent.workflow.evaluate <folder>` to check the recommendations.
4. Write 3–5 real past requests as YAML (including `team_handling`), run `python -m agent.workflow.evaluate <folder>`, review `report.md` / `mistakes.csv`.
5. Hook up the real Teams webhook (`python -m agent.integrations.teams <url>` first).
6. Set `ACCOUNTS` (the Data Team account; requesters self-register) and demo to the team following [DEMO.md](../DEMO.md): one person as requester, one as the Data Team.

## After the prototype
From [PLAN.md](../PLAN.md):
1. Run on a VM with Docker (the compose file is ready, PostgreSQL included)
2. Model: Ollama/vLLM on a GPU VM, or an LLM API approved by the company
3. Teams bot to approve directly in the thread (replaces the review tab + key)
4. Create real User Stories in Azure DevOps / Jira
5. Read lake metadata (e.g. the first `ingest_date` per table) to turn the history risk into a real date check
6. Idea, to plan once the Data Team has used the flow: after approval, a list of User Stories per kind of work instead of job YAML (jobs are configured in the ingestion UI). New job or new connection: non-prod, then prod (own connection with `kv://` secrets, PR merge, backfill). Source with no template: a spike first, its open questions as acceptance criteria

**MCP for GitHub:** the repos are currently read straight through the GitHub API (more reliable with small models). Once tool calling is stable (after Phase 0), a GitHub MCP server could let the agent read a model's SQL when it needs more detail (e.g. "does this model filter on X?").
