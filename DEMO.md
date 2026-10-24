# Phase 5 – Team demo runbook

About 20 minutes. Goal: show the 3 things the prototype must prove (see `PLAN.md`), then collect feedback on the User Stories. Everything shown comes from the real platform repos; there is no demo data.

## Before the demo
1. **Model** (optional): host it on Colab (README → Step 1). Without it the agent runs rule-based. That is fine for the flow, but the questions and User Story text are plainer.
2. **Docker (Codespaces)**: after `up -d`, `docker compose -f infrastructure/non-prod/docker-compose.yml logs app --tail 15` must show `Running on local URL`. A `PoolTimeout` or "DNS lookup of api.github.com failed" means the codespace's legacy firewall blocks the compose network. `.devcontainer/` fixes it on every start; otherwise run `bash infrastructure/non-prod/codespace-network.sh`, then `restart app` ([runbook](infrastructure/README.md#codespaces-containers-cant-reach-each-other-or-the-internet)).
3. **Repositories**: set `GITHUB_TOKEN` (read access to both repos; in Codespaces `PLATFORM_GITHUB_TOKEN`), or `INGESTION_PATH` / `TRANSFORMATION_PATH` to local checkouts. In the app, **⚙️ Settings → Repositories** must list the systems, jobs and dbt models with no error. Today that is system `crm`, job `crm-customers-daily`, models `stg_crm__customers` and `crm_customers_current`, and source template `sqlserver`.
4. **Teams**: create a channel workflow *"Post to a channel when a webhook request is received"*, then:
   ```powershell
   .venv\Scripts\python -m agent.integrations.teams "<webhook url>"   # check a test card shows up
   $env:TEAMS_WEBHOOK_URL = "<webhook url>"
   ```
   If a post fails during the demo, the flow keeps going and the message is saved to `outputs/<request_id>/teams_messages.jsonl` (with `webhook_error`).
5. **Past requests** (optional): write 3–5 real past requests as YAML (format in [agent/workflow/evaluate.py](agent/workflow/evaluate.py)) and run `.venv\Scripts\python -m agent.workflow.evaluate <folder>`; read `outputs/eval/<run>/report.md` before the demo so you know where the agent goes wrong.
6. **Accounts**: only the Data Team needs one, e.g.
   ```powershell
   $env:ACCOUNTS = "data.team@gmail.com:<password>"
   ```
   `data.team@gmail.com` is the Data Team by default (`DATA_TEAM` to change it). Requesters sign in with their own email: the first sign-in sets their password (at least 8 characters), and they only see Request and their own Sessions.
7. Start the app: `.venv\Scripts\python app.py`. Use two browser windows (one private): one signed in as the requester, one as the Data Team.

## Script
| # | Show | Point to make |
|---|---|---|
| 1 | Example "Current CRM customers for a dashboard" | Asks only for missing fields, at most 3 per turn; recommends the existing dbt model `crm_customers_current`, so nothing new is ingested |
| 2 | Teams channel | "New data request" card arrives right after intake |
| 3 | Example "CRM segments" | CRM is onboarded but `segments` has no ingestion job: proposes a job on `crm-sqlserver-nonprod`, then dbt models |
| 4 | Example "HR employees on SQL Server" | Not onboarded, but SQL Server is a supported source type: proposes a new connection from the `sqlserver` template, a job and dbt models |
| 4b | "ERP on PostgreSQL", reply `ok` | No PostgreSQL template yet: the agent reads public docs and lists questions for the Data Team; findings are marked unverified |
| 5 | **🛡 Data Team review** tab (as the Data Team): open the request, **Request changes** with a comment, show the requester's page updating, then **Approve** | The Data Team approves before anything is drafted, not the requester; changes re-run feasibility |
| 6 | `outputs/<request_id>/user_story.md` + summary card in Teams | Every step points to a file in one of the two repos. Ask the team: usable as is, with minor edits, or not? |

## Collect
- A rating per User Story (fill in the *Reviewer rating* column in `report.md`). Target: "usable, minor edits".
- Notes in the `reviewer_notes` column of `mistakes.csv`: was the agent wrong, or does a repo miss something (a job, a connection, a model)?
