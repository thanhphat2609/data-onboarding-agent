# Infrastructure

The web UI runs in Docker. One `Dockerfile` and one `docker-compose.yml` cover a laptop, a VM and GitHub Codespaces, and the command is the same everywhere.

```
infrastructure/
├── Dockerfile          # two stages: requirements into a venv, then slim runtime + agent/ + app.py; port 7860
├── docker-compose.yml  # app (builds the image, port, settings, outputs/) + postgres (sessions, Airflow metadata DB)
├── postgres/init/      # first-start script: databases onboarding_agent + airflow, one role each
├── .env.example        # settings template; copy to .env (gitignored)
└── README.md           # this file
```

```
 Browser                Docker host (laptop / VM / codespace)                Google Colab (GPU), optional
┌───────────────┐      ┌───────────────────────────────────────────┐ HTTPS   ┌──────────────────────────┐
│ 127.0.0.1:7860│─────▶│ container "app": python app.py (Gradio)   │ + key   │ cloudflared tunnel       │
│ (or Codespaces│      │   └─ outputs/   ◀── bind mount             ├────────▶│  └─ ollama_auth_proxy.py │
│  PORTS tab)   │      └──────────────────┬────────────────────────┘         │      └─ Ollama (qwen2.5) │
└───────────────┘                         │ GITHUB_TOKEN                     └──────────────────────────┘
                                          ▼
                     github.com: data-onboarding-ingestion, data-onboarding-transformation
```

## Open the UI

### 1. (Optional) Settings
All settings are optional. Without them the agent runs rule-based, Teams messages are written to `outputs/`, and you can type the model host and API key straight into the Settings tab. Only `GITHUB_TOKEN` is needed in practice: without it the agent can't read the two private platform repos.

```bash
cp infrastructure/.env.example infrastructure/.env      # PowerShell: Copy-Item infrastructure/.env.example infrastructure/.env
```

| Variable | Value |
|---|---|
| `OLLAMA_HOST` | Tunnel URL from the Colab notebook, step 4 (`https://xxxx.trycloudflare.com`). Empty = Ollama on the host machine |
| `OLLAMA_API_KEY` | API key printed by the same Colab cell |
| `OLLAMA_MODEL` | e.g. `qwen2.5:7b`. Empty = rule-based |
| `GITHUB_TOKEN` | Fine-grained token, **Contents: Read-only** on data-onboarding-ingestion and data-onboarding-transformation; the agent reads both |
| `INGESTION_REPO` / `INGESTION_REF`, `TRANSFORMATION_REPO` / `TRANSFORMATION_REF` | Other repos or branches to read (defaults: the two platform repos, `main`) |
| `TEAMS_WEBHOOK_URL` | Teams Workflows webhook. Empty = messages go to `outputs/<request_id>/teams_messages.jsonl` |
| `ACCOUNTS` | Web UI logins, `user:password` pairs separated by commas. Empty = no login, everyone sees every tab |
| `DATA_TEAM` | Accounts with full access (🛡 Data Team review, Settings, Debug, every session), comma-separated. Default `data.team@gmail.com`. Other accounts only see Request and their own Sessions |
| `WEB_RESEARCH` | `0` turns off web research for sources the platform can't onboard yet |
| `WITH_BROWSER` | `true` builds the image with headless Chromium for web research (Bing/Brave search, JavaScript-only pages); adds ~400 MB. Needs `up -d --build` |
| `UI_PORT` | Host port, default `7860` |
| `POSTGRES_PASSWORD`, `POSTGRES_AGENT_PASSWORD`, `POSTGRES_AIRFLOW_PASSWORD`, `POSTGRES_PLATFORM_PASSWORD` | Passwords of the `postgres` superuser and the `agent`, `airflow` and `platform` roles (defaults: the role name; the port is localhost-only). Read **only on the first start**, when the `pgdata` volume is empty. Use URL-safe characters. The ingestion repo's `.env` repeats the last two as `AIRFLOW_DB_PASSWORD` / `PLATFORM_DB_PASSWORD` |
| `POSTGRES_PORT` | Host port of PostgreSQL, default `5432` |
| `DATABASE_URL` | Override to use an external PostgreSQL instead of the `postgres` container |
Env vars already set in your shell override `.env`, so Codespaces secrets with these names are picked up automatically.

### 2. Start
From the repo root:
```bash
docker compose -f infrastructure/docker-compose.yml up -d --build
```
The first build takes a few minutes. After that, open:

- **Laptop:** http://127.0.0.1:7860
- **GitHub Codespaces:** a notification *"Your application running on port 7860 is available"* appears; click **Open in Browser**. You can also open the **PORTS** tab (next to TERMINAL) and click the 🌐 icon on port 7860. The URL looks like `https://<codespace-name>-7860.app.github.dev`.
- **VM:** from your laptop, run `ssh -L 7860:127.0.0.1:7860 user@vm`, then open http://127.0.0.1:7860.

From there, everything works as in the main README: the **⚙️ Settings** tab (LLM: Fetch models → Test → Apply; check both repos were read), then chat in the **💬 Request** tab; the Data Team approves in the **🛡 Data Team review** tab.

### 3. Day-to-day commands
```bash
docker compose -f infrastructure/docker-compose.yml ps             # running? healthy?
docker compose -f infrastructure/docker-compose.yml logs -f        # follow the log
docker compose -f infrastructure/docker-compose.yml up -d --build  # after changing code or requirements.txt (code is copied into the image)
docker compose -f infrastructure/docker-compose.yml up -d          # after editing .env (restart does not re-read it)
docker compose -f infrastructure/docker-compose.yml down           # stop; outputs/ and the pgdata volume are kept
docker compose -f infrastructure/docker-compose.yml exec postgres psql -U agent -d onboarding_agent   # query sessions (docs/POSTGRESQL.md)
docker compose -f infrastructure/docker-compose.yml exec app python -m agent.integrations.teams   # send a Teams test card from the container
```

## Where the data lives

Both survive `down` and rebuilds:

| Where | Contents |
|---|---|
| `postgres` container (PostgreSQL 16), volume `pgdata` | Database `onboarding_agent`: sessions (LangGraph checkpoints + the `sessions` table). Databases `airflow` (Airflow's metadata DB) and `platform` (run records) for [data-onboarding-ingestion](https://github.com/thanhphat2609/data-onboarding-ingestion). Queries and layout: [docs/POSTGRESQL.md](../docs/POSTGRESQL.md) |
| `outputs/` on the host (bind mount `/app/outputs`) | User stories, feasibility, Teams messages, eval reports |

`down -v` deletes the `pgdata` volume, so **every session, Airflow's metadata and the ingestion run records** go with it.

The init script ([postgres/init/01-databases.sh](postgres/init/01-databases.sh)) creates the three databases and their roles on the first start only. Sessions saved earlier in `outputs/checkpoints.db` (SQLite) aren't moved over; open that file with `CHECKPOINT_DB` and no `DATABASE_URL` to read them.

**Sharing the server with Airflow.** On the demo VM 1 (Agent + Airflow + Flink JobManager; TaskManagers on VM 2), this server is also Airflow's metadata DB. The `postgres` container joins the Docker network `data-platform`, which this compose file creates. The ingestion repo's compose joins it as an external network, and Airflow connects to `postgres:5432`, database `airflow`, user `airflow`. Start this stack first. This only works with both stacks on one Docker host; a standalone ingestion codespace runs its own Postgres instead (its `local-db` profile).

## GitHub Codespaces notes

- **Docker is already there.** The default Codespaces image includes Docker, so no extra setup is needed. Open the codespace and run the command from step 2.
- **Secrets:** add the variables above under **GitHub → Settings → Codespaces → Secrets** and give them access to this repo, or use `infrastructure/.env`. `GITHUB_TOKEN` is special in Codespaces: the codespace presets its own, which can only read the repo it was opened from, and a shell variable wins over `.env`. Run `export GITHUB_TOKEN=<your token>` in the terminal before `docker compose up`.
- **Who can open the URL:** the port is **Private** by default, so only you, signed in to GitHub, can open it. Keep it that way: the app's own login (`ACCOUNTS`) is a prototype's, with plain-text passwords and no rate limit. For a team demo, right-click the port → **Port visibility → Private to Organization**. Avoid **Public**.
- **Persistence:** `outputs/` is under `/workspaces`, so they survive stopping the codespace but **are lost when the codespace is deleted**. Inactive codespaces are deleted after 30 days by default. Copy any `outputs/` you need, since that folder is gitignored.
- **Restarts:** after the codespace is stopped and reopened, run `docker compose -f infrastructure/docker-compose.yml up -d` again if the UI isn't in PORTS.

## Model

- **Colab-hosted:** set `OLLAMA_HOST` and `OLLAMA_API_KEY`, or paste them in the ⚙️ Settings tab. The tunnel URL changes every time the Colab cell is re-run.
- **Ollama on the same machine:** leave `OLLAMA_HOST` empty; it defaults to `http://host.docker.internal:11434`. Inside the container, `localhost` is the container itself, not your machine.

## Security

The port is published on **127.0.0.1 only** because the app's login is only a prototype's (plain-text passwords from env, no TLS) and the Settings tab accepts any host and API key. Don't change the binding to `0.0.0.0` on a VM. Use an SSH tunnel, or put a reverse proxy with authentication in front. Don't use `--share`, which creates a public Gradio link.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Container keeps restarting / `unhealthy` | `docker compose -f infrastructure/docker-compose.yml logs app` |
| Codespaces: port 7860 not in PORTS | Check with `docker compose -f infrastructure/docker-compose.yml ps`. If it's running, add it by hand: PORTS → **Forward a Port** → `7860` |
| Linux / VM: `Permission denied` writing `outputs/` | The container runs as uid 1000. Run `sudo chown -R 1000:1000 outputs` |
| `Fetch models` fails | The Colab tab is closed or the tunnel URL changed. Re-run notebook step 4. For host Ollama, use `host.docker.internal`, not `localhost` |
| Settings → Repositories: "DNS lookup of api.github.com failed" | The container has no working DNS; the token is not the problem. Containers use Docker's default DNS (the host's resolver). Public resolvers such as 1.1.1.1 / 8.8.8.8 do **not** answer from a Codespace's Docker (tested 2026-10-24), so don't hard-code them. Check with `docker compose -f infrastructure/docker-compose.yml exec app python -c "import socket; print(socket.gethostbyname('api.github.com'))"` and compare with `cat /etc/resolv.conf` / `getent hosts api.github.com` on the host. The agent retries a failed load by itself after 60 s |
| `app` waits forever / `dependency failed to start: container data-onboarding-postgres is unhealthy` | `docker compose -f infrastructure/docker-compose.yml logs postgres`. An init-script error (e.g. `$'\r': command not found` = the script was checked out with Windows line endings) means the databases weren't created. Fix it, then `down -v` (**deletes the database**) and `up -d` |
| `network data-platform was found but has incorrect label` | The ingestion repo's `bootstrap.sh` created the network first (standalone mode). Stop the ingestion stack, `docker network rm data-platform`, start this stack, then the ingestion stack |
| `password authentication failed for user "agent"` | The passwords in `.env` changed after the first start; the volume keeps the old ones. `ALTER ROLE agent PASSWORD '…'` as `postgres`, or `down -v` on a throwaway setup |
| Header pill "Repos not readable" / 404 in Settings → Repositories | `GITHUB_TOKEN` is missing or can't read one of the repos (in Codespaces: the preset token). Export a token with read access to both, then `up -d` |
| `port is already allocated` | Something else uses 7860. Set `UI_PORT=7861` in `.env` and open that port instead |
