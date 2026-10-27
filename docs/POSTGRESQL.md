# PostgreSQL: where the agent's data lives, and how to check it after a demo

> In Docker compose, sessions are in PostgreSQL (`DATABASE_URL`). Without `DATABASE_URL` (laptop venv, Colab), the same tables are in SQLite at `CHECKPOINT_DB`; see [SQLite](#sqlite-laptop-colab).

## Layout

One PostgreSQL server holds separate databases, each with its own owner. The agent and Airflow never share a database or schema.

```
postgres 16 (container data-onboarding-postgres, volume pgdata)
├── airflow            ← Airflow metadata (owner: airflow). Airflow's sql_alchemy_conn points here
├── platform           ← data-onboarding-ingestion run records: runs, run_events (owner: platform, from its Phase 5)
└── onboarding_agent   ← this app (owner: agent)
    ├── sessions               one row per chat session: who, status, review   (ours, easy to query)
    ├── requesters             self-registered logins: email, scrypt password hash, created_at (ours)
    ├── source_docs            docs links learned from approved requests, per source: url, title, times approved (ours)
    ├── checkpoints            LangGraph: one row per graph step per session
    ├── checkpoint_blobs       LangGraph: state values (binary, msgpack)
    ├── checkpoint_writes      LangGraph: pending writes of a step (binary)
    └── checkpoint_migrations  LangGraph: schema version
```

All three databases and roles are created by [infrastructure/postgres/init/01-databases.sh](../infrastructure/postgres/init/01-databases.sh) on the first start. The app creates its own tables when it starts.

Why they're kept apart:
- `airflow db migrate` owns the Airflow schema and changes it on upgrades, so no other tables go in it.
- A bug in the agent can't touch DAG run history, and Airflow can't touch sessions. Each database can be backed up and restored by itself.
- The agent never reads Airflow's tables. For job run status it would call the Airflow REST API (`/api/v2/dags/{dag_id}/dagRuns`).

### Roles and passwords

Four login roles, four different passwords. In prod each is a GitHub secret of this repository, written into `infrastructure/prod/.env` on VM 1 by the Deploy workflow ([infrastructure/prod/README.md](../infrastructure/prod/README.md#github-setup-settings-of-this-repository)):

| Role | Password | Can reach | Used by | Same value also in data-onboarding-ingestion's GitHub secrets |
|---|---|---|---|---|
| `postgres` (superuser) | `POSTGRES_PASSWORD` | Everything | Nobody day to day: the init script on the first start, then you for admin work (`ALTER ROLE … PASSWORD`, a new database, backups, debugging). Required by the `postgres` image | No |
| `agent` | `POSTGRES_AGENT_PASSWORD` | `onboarding_agent` | This app (`DATABASE_URL`) | No |
| `airflow` | `POSTGRES_AIRFLOW_PASSWORD` | `airflow` | Airflow (scheduler, API server) | Yes, same value as `AIRFLOW_DB_PASSWORD` |
| `platform` | `POSTGRES_PLATFORM_PASSWORD` | `platform` | data-onboarding-ingestion's run history, from its Phase 5. **Empty until then** | Not yet; as `PLATFORM_DB_PASSWORD` once its prod stack uses the run records |

Each role can only reach its own database (`REVOKE ALL … FROM PUBLIC`), so a leaked Airflow password can't read sessions, and the other way round. Use URL-safe characters (`openssl rand -hex 24`): the passwords go into connection URLs.

### Why a `platform` database next to `airflow`

Today only `onboarding_agent` and `airflow` are used. `platform` is reserved for data-onboarding-ingestion's own run records (its architecture §3.4, roadmap Phase 5):

| Table | Content |
|---|---|
| `runs` | One row per ingestion run: `ingest_date`, Flink job id, expected vs. written rows, output paths, the resolved job spec, the error |
| `run_events` | Every state change and diagnostic of a run, append-only |

They feed the run history in ingestion's UI (state, counts, duration, errors, links). They don't go in the `airflow` database because:
- **Airflow owns that schema.** `airflow db migrate` changes it on upgrades and `airflow db clean` purges old runs: it is operational state, not a record to keep.
- **Airflow doesn't model what the platform needs:** Flink job ids, row counts, output paths, the resolved spec.
- **Own role, own password:** the run records survive Airflow upgrades and clean-ups, and Airflow can't change them.

It is created now, empty, because the init script only runs on the **first start** (empty `pgdata` volume). Added later, it would mean creating the role and database by hand as the superuser on the live server. Keeping it costs one generated password.

Airflow (data-onboarding-ingestion) reaches the server over the shared Docker network `data-platform` as `postgres:5432`, database `airflow`, user `airflow`. That needs both stacks on one Docker host, as on the demo VM 1 (Agent + Airflow + Flink JobManager). Decision record on the ingestion side: its ADR-0011.

## The `sessions` table

LangGraph stores the state as binary blobs, so SQL can't read it. `sessions` ([agent/workflow/sessions.py](../agent/workflow/sessions.py)) holds the facts you want to check, in plain columns. The runner writes the row after every graph run (new request, answer, review) and records the reviewer on a Data Team decision. Sessions that existed before the table get their row when the app starts.

| Column | Meaning |
|---|---|
| `thread_id` | Primary key; the same id the UI shows as "Current thread_id" |
| `request_id` | `REQ-YYYYMMDD-xxxxxx` |
| `created_by` | Login that typed the request (can be a Data Team member) |
| `requested_by` | Business owner of the request: `created_by`, or the **On behalf of** login a Data Team member entered |
| `reviewed_by`, `review_action`, `reviewed_at` | Last Data Team decision: who, `approve` / `edit` (= Request changes), when |
| `status` | `empty` (started), `question` (waiting for the requester), `approval` (waiting for Data Team review), `done` |
| `sources` | Source systems, comma-separated, e.g. `crm` |
| `description` | The request's dataset description |
| `created_at`, `updated_at` | `timestamptz` (SQLite: ISO text, UTC) |

A requester sees a session when `requested_by` or `created_by` is them. The Data Team sees all sessions. Without a login, both columns are empty.

## Connect

From the Docker host (laptop, VM or Codespace):

```bash
docker exec -it data-onboarding-postgres psql -U agent -d onboarding_agent
```

From a desktop client (DBeaver, pgAdmin): host `127.0.0.1`, port `5432` (`POSTGRES_PORT`), database `onboarding_agent`, user `agent`. The password is `POSTGRES_AGENT_PASSWORD` in `infrastructure/non-prod/.env`, default `agent`. The port is published on localhost only, so on Codespaces forward it from the PORTS tab, and on a VM use an SSH tunnel (`ssh -L 5432:127.0.0.1:5432 user@vm`).

Useful `psql` commands: `\dt` lists tables, `\d sessions` shows columns, `\x auto` makes wide rows readable, `\q` quits.

## After the demo: what to check

### What happened
```sql
-- Every session of the demo, newest first
SELECT request_id, requested_by, created_by, status, sources, created_at, updated_at
FROM sessions
WHERE created_at >= now() - interval '1 day'
ORDER BY created_at DESC;

-- How many sessions ended in each status
SELECT status, count(*) FROM sessions
WHERE created_at >= now() - interval '1 day'
GROUP BY status ORDER BY count(*) DESC;

-- Sessions per requester
SELECT requested_by, count(*) AS sessions, count(*) FILTER (WHERE status = 'done') AS done
FROM sessions GROUP BY requested_by ORDER BY sessions DESC;
```

### Review
```sql
-- Still waiting for the Data Team
SELECT request_id, requested_by, sources, now() - updated_at AS waiting_for
FROM sessions WHERE status = 'approval' ORDER BY updated_at;

-- Who reviewed what, and how long it took from request to the last decision
SELECT request_id, requested_by, reviewed_by, review_action, reviewed_at - created_at AS time_to_review
FROM sessions WHERE reviewed_at IS NOT NULL ORDER BY reviewed_at DESC;

-- Sessions a Data Team member filed for someone else
SELECT request_id, created_by, requested_by FROM sessions WHERE created_by <> requested_by;
```

### Stuck or odd sessions
```sql
-- Waiting for the requester's answer for more than an hour
SELECT request_id, requested_by, updated_at FROM sessions
WHERE status = 'question' AND updated_at < now() - interval '1 hour';

-- Graph steps per session: a very high number means the agent kept asking
SELECT s.request_id, count(*) AS steps
FROM sessions s JOIN checkpoints c ON c.thread_id = s.thread_id AND c.checkpoint_ns = ''
GROUP BY s.request_id ORDER BY steps DESC;

-- Checkpoints with no sessions row (should be empty after a start; otherwise a runner bug)
SELECT DISTINCT c.thread_id FROM checkpoints c
LEFT JOIN sessions s ON s.thread_id = c.thread_id
WHERE s.thread_id IS NULL;
```

### Export for the demo notes
```bash
docker exec data-onboarding-postgres psql -U agent -d onboarding_agent \
  -c "\copy (SELECT * FROM sessions WHERE created_at >= now() - interval '1 day' ORDER BY created_at) TO STDOUT CSV HEADER" \
  > demo_sessions.csv
```

### The full state of one session
SQL can't decode the blobs, so the agent's own code reads them (works with PostgreSQL and SQLite):

```bash
docker exec data-onboarding-agent python -c "
import json, sys
from agent.workflow.runner import AgentRunner
print(json.dumps(AgentRunner().state(sys.argv[1]), indent=2, ensure_ascii=False, default=str))
" <thread_id>
```

The User Story, feasibility and Teams messages for each request are also files in `outputs/<request_id>/`.

### Who signed in
```sql
-- Requesters who self-registered (the Data Team is configured in ACCOUNTS, not stored here)
SELECT email, created_at FROM requesters ORDER BY created_at DESC;

-- Reset a forgotten password: their next sign-in sets a new one; their sessions are kept
DELETE FROM requesters WHERE email = 'alice@gmail.com';
```

### Docs links the agent has learned

Every request the Data Team approves stores the top links of each source it researched; the next request for that source reads them first ([learned.py](../agent/research/learned.py)).

```sql
SELECT source, approved, url, title, last_approved_at FROM source_docs ORDER BY source, approved DESC;

-- Forget a wrong link
DELETE FROM source_docs WHERE source = 'google search console' AND url = 'https://…';
```

## Clean up test sessions

Delete only sessions you created for testing. Check the list first:

```sql
SELECT thread_id, request_id, requested_by FROM sessions WHERE requested_by = 'test.user@gmail.com';

BEGIN;
DELETE FROM checkpoint_writes WHERE thread_id = '<thread_id>';
DELETE FROM checkpoint_blobs  WHERE thread_id = '<thread_id>';
DELETE FROM checkpoints       WHERE thread_id = '<thread_id>';
DELETE FROM sessions          WHERE thread_id = '<thread_id>';
COMMIT;
```

Then delete `outputs/<request_id>/` for the same requests. To wipe everything (sessions **and** Airflow's metadata), `docker compose -f infrastructure/non-prod/docker-compose.yml down -v`.

## SQLite (laptop, Colab)

Without `DATABASE_URL`, everything is in one file: `CHECKPOINT_DB` (default `./checkpoints.db`), with the same `sessions` table. Open it with DB Browser for SQLite or DBeaver; stop the app first so the file isn't being written to. The queries above work with small changes: no `interval` / `FILTER`, timestamps are ISO text (`WHERE created_at >= '2026-10-24'`).

Sessions saved in the old Docker location `outputs/checkpoints.db` aren't moved to PostgreSQL. To read them, run the app outside Docker with `CHECKPOINT_DB=outputs/checkpoints.db`.
