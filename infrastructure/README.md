# Infrastructure

The web UI runs in Docker, with the same layout as data-onboarding-ingestion: one folder per environment, sharing the image and the PostgreSQL init script.

```
infrastructure/
├── Dockerfile              # two stages: requirements into a venv, then slim runtime + agent/ + app.py; port 7860
├── postgres/init/          # first-start script: databases onboarding_agent, airflow, platform; one role each
├── non-prod/               # laptop and GitHub Codespaces (this README)
│   ├── docker-compose.yml  #   app (builds the image, port, settings, outputs/) + postgres
│   ├── .env.example        #   settings template; copy to non-prod/.env (gitignored)
│   └── codespace-network.sh #  Codespaces firewall fix, run on every start by .devcontainer/devcontainer.json
├── prod/                   # VM 1 (Agent + Airflow + Flink JobManager): compose, .env.example, deploy.sh; draft until the VM exists (prod/README.md)
└── README.md               # this file
```

Prod differs from non-prod in what it enforces: required passwords, `ACCOUNTS` and `PLATFORM_GITHUB_TOKEN` (`${…:?}`), and backups of the `pgdata` volume. The image is built on the VM by the Deploy workflow on every push to `main` that passes CI ([prod/README.md](prod/README.md)).

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
All settings are optional. Without them the agent runs rule-based, Teams messages are written to `outputs/`, and you can type the model host and API key straight into the Settings tab. In practice you need a GitHub token (the agent can't read the two private platform repos without it) and `ACCOUNTS` if you want the login page.

```bash
cp infrastructure/non-prod/.env.example infrastructure/non-prod/.env      # PowerShell: Copy-Item infrastructure/non-prod/.env.example infrastructure/non-prod/.env
```

| Variable | Value |
|---|---|
| `OLLAMA_HOST` | Tunnel URL from the Colab notebook, step 4 (`https://xxxx.trycloudflare.com`). Empty = Ollama on the host machine |
| `OLLAMA_API_KEY` | API key printed by the same Colab cell |
| `OLLAMA_MODEL` | e.g. `qwen2.5:7b`. Empty = rule-based |
| `PLATFORM_GITHUB_TOKEN` (or `GITHUB_TOKEN`) | Fine-grained token, **Contents: Read-only** on data-onboarding-ingestion and data-onboarding-transformation; the agent reads both. `PLATFORM_GITHUB_TOKEN` wins; use it in Codespaces (see below) |
| `INGESTION_REPO` / `INGESTION_REF`, `TRANSFORMATION_REPO` / `TRANSFORMATION_REF` | Other repos or branches to read (defaults: the two platform repos, `main`) |
| `TEAMS_WEBHOOK_URL` | Teams Workflows webhook. Empty = messages go to `outputs/<request_id>/teams_messages.jsonl` |
| `ACCOUNTS` | Web UI logins, `user:password` pairs separated by commas. Usually only the Data Team, e.g. `data.team@gmail.com:<password>`: any other email is a requester and self-registers (its first sign-in sets its password, min. 8 characters). Empty = no login, everyone sees every tab |
| `DATA_TEAM` | Accounts with full access (🛡 Data Team review, Settings, Debug, every session), comma-separated. Default `data.team@gmail.com`. Other accounts only see Request and their own Sessions |
| `WEB_RESEARCH` | `0` turns off web research for sources the platform can't onboard yet |
| `WITH_BROWSER` | `true` builds the image with headless Chromium for web research (Bing/Brave search, JavaScript-only pages); adds ~400 MB. Needs `up -d --build` |
| `UI_PORT` | Host port, default `7860` |
| `POSTGRES_PASSWORD`, `POSTGRES_AGENT_PASSWORD`, `POSTGRES_AIRFLOW_PASSWORD`, `POSTGRES_PLATFORM_PASSWORD` | Passwords of the `postgres` superuser and the `agent`, `airflow` and `platform` roles (defaults: the role name; the port is localhost-only). Read **only on the first start**, when the `pgdata` volume is empty. Use URL-safe characters. The ingestion repo's `.env` repeats the last two as `AIRFLOW_DB_PASSWORD` / `PLATFORM_DB_PASSWORD` |
| `POSTGRES_PORT` | Host port of PostgreSQL, default `5432` |
| `DATABASE_URL` | Override to use an external PostgreSQL instead of the `postgres` container |

Env vars already set in your shell override `.env`, so Codespaces secrets with these names are picked up automatically. After editing `.env`, run `up -d` (a `restart` doesn't re-read it).

### 2. Start
From the repo root:
```bash
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
```
The first build takes a few minutes. After that, open:

- **Laptop:** http://127.0.0.1:7860
- **GitHub Codespaces:** a notification *"Your application running on port 7860 is available"* appears; click **Open in Browser**. You can also open the **PORTS** tab (next to TERMINAL) and click the 🌐 icon on port 7860. The URL looks like `https://<codespace-name>-7860.app.github.dev`.
- **VM:** from your laptop, run `ssh -L 7860:127.0.0.1:7860 user@vm`, then open http://127.0.0.1:7860.

From there, everything works as in the main README: the **⚙️ Settings** tab (LLM: Fetch models → Test → Apply; check both repos were read), then chat in the **💬 Request** tab; the Data Team approves in the **🛡 Data Team review** tab.

### 3. Day-to-day commands
```bash
docker compose -f infrastructure/non-prod/docker-compose.yml ps             # running? healthy?
docker compose -f infrastructure/non-prod/docker-compose.yml logs -f        # follow the log
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build  # after changing code or requirements.txt (code is copied into the image)
docker compose -f infrastructure/non-prod/docker-compose.yml up -d          # after editing .env (restart does not re-read it)
docker compose -f infrastructure/non-prod/docker-compose.yml down           # stop; outputs/ and the pgdata volume are kept
docker compose -f infrastructure/non-prod/docker-compose.yml exec postgres psql -U agent -d onboarding_agent   # query sessions (docs/POSTGRESQL.md)
docker compose -f infrastructure/non-prod/docker-compose.yml exec app python -m agent.integrations.teams   # send a Teams test card from the container
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

- **Docker is already there.** [.devcontainer/devcontainer.json](../.devcontainer/devcontainer.json) uses the default Codespaces image (Docker included), forwards port 7860 and fixes the container firewall on every start (below). Open the codespace and run the command from step 2.
- **Secrets:** add the variables above under **GitHub → Settings → Codespaces → Secrets** and give them access to this repo, or use `infrastructure/non-prod/.env`. `GITHUB_TOKEN` is special in Codespaces: the codespace presets its own, which can only read the repo it was opened from (so both platform repos give 404), it wins over `.env`, and GitHub doesn't allow a secret named `GITHUB_*`. Add your token as the Codespaces secret **`PLATFORM_GITHUB_TOKEN`** instead; the agent prefers it. Secrets and `ACCOUNTS` reach a running codespace only after it restarts (or `export` them in the terminal, then `up -d`).
- **Who can open the URL:** the port is **Private** by default, so only you, signed in to GitHub, can open it. Keep it that way: the app's own login is a prototype's: anyone who can open the URL can self-register as a requester, the Data Team password is plain text in env, and there is no rate limit. For a team demo, right-click the port → **Port visibility → Private to Organization**. Avoid **Public**.
- **Persistence:** `outputs/` is under `/workspaces`, so they survive stopping the codespace but **are lost when the codespace is deleted**. Inactive codespaces are deleted after 30 days by default. Copy any `outputs/` you need, since that folder is gitignored.
- **Restarts:** after the codespace is stopped and reopened, run `docker compose -f infrastructure/non-prod/docker-compose.yml up -d` again if the UI isn't in PORTS.
- **Container networking is blocked in a fresh codespace, fixed automatically.** Codespaces load two firewalls at once: Docker 29 writes its rules to `nf_tables`, while old `iptables-legacy` rules with `-P FORWARD DROP` only let the default `docker0` bridge through. The compose network is a separate bridge, so its traffic is dropped. Symptoms: the app restarts with `PoolTimeout` / `connection timeout expired` (it can't reach `postgres`), and "DNS lookup of api.github.com failed". [non-prod/codespace-network.sh](non-prod/codespace-network.sh) fixes it on every codespace start (`postStartCommand`); details in [Codespaces: containers can't reach each other or the internet](#codespaces-containers-cant-reach-each-other-or-the-internet).

### Codespaces: containers can't reach each other or the internet

Seen on 2026-10-24 (Docker 29.8, `iptables v1.8.10 (nf_tables)`) and again in a brand-new codespace on 2026-10-25: every new codespace starts with the rule. Since then `codespace-network.sh` runs on each start. A codespace created before `.devcontainer/` existed doesn't run it: use step 2, or `bash infrastructure/non-prod/codespace-network.sh`.

**1. Confirm it.** Docker's default network works, the compose network doesn't:

```bash
docker run --rm alpine nslookup api.github.com                                                   # works
docker run --rm --network data-onboarding-agent_default alpine nslookup api.github.com           # times out
docker run --rm --network data-onboarding-agent_default alpine nc -zv -w 3 postgres 5432         # times out
sudo iptables -S FORWARD | tail -1        # "# Warning: iptables-legacy tables present"
sudo iptables-legacy -S FORWARD           # "-P FORWARD DROP" and rules for docker0 only
```

**2. Fix it** (changes only this codespace's firewall), then check and restart the app:

```bash
sudo iptables-legacy -P FORWARD ACCEPT
docker run --rm --network data-onboarding-agent_default alpine nc -zv -w 3 postgres 5432         # "open"
docker compose -f infrastructure/non-prod/docker-compose.yml restart app
docker compose -f infrastructure/non-prod/docker-compose.yml logs app --tail 15                           # "Running on local URL"
```

The app container keeps restarting until it reaches PostgreSQL, so after the fix it also recovers by itself within a minute. Don't work around it with hard-coded DNS servers in compose: public resolvers (1.1.1.1 / 8.8.8.8) don't answer from a codespace, and the database connection would still be blocked.

## Model

- **Colab-hosted:** set `OLLAMA_HOST` and `OLLAMA_API_KEY`, or paste them in the ⚙️ Settings tab. The tunnel URL changes every time the Colab cell is re-run.
- **Ollama on the same machine:** leave `OLLAMA_HOST` empty; it defaults to `http://host.docker.internal:11434`. Inside the container, `localhost` is the container itself, not your machine.

## Security

The port is published on **127.0.0.1 only** because the app's login is only a prototype's (plain-text passwords from env, no TLS) and the Settings tab accepts any host and API key. Don't change the binding to `0.0.0.0` on a VM. Use an SSH tunnel, or put a reverse proxy with authentication in front. Don't use `--share`, which creates a public Gradio link.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Container keeps restarting / `unhealthy` | `docker compose -f infrastructure/non-prod/docker-compose.yml logs app` |
| Codespaces: port 7860 not in PORTS | Check with `docker compose -f infrastructure/non-prod/docker-compose.yml ps`. If it's running, add it by hand: PORTS → **Forward a Port** → `7860` |
| Linux / VM: `Permission denied` writing `outputs/` | The container runs as uid 1000. Run `sudo chown -R 1000:1000 outputs` |
| `Fetch models` fails | The Colab tab is closed or the tunnel URL changed. Re-run notebook step 4. For host Ollama, use `host.docker.internal`, not `localhost` |
| Settings → Repositories: "DNS lookup of api.github.com failed" | The container can't reach the network; the token is not the problem. In Codespaces this is the legacy firewall rule: [fix](#codespaces-containers-cant-reach-each-other-or-the-internet). Elsewhere, compare `docker compose -f infrastructure/non-prod/docker-compose.yml exec app python -c "import socket; print(socket.gethostbyname('api.github.com'))"` with `getent hosts api.github.com` on the host. The agent retries a failed load by itself after 60 s |
| App restarts with `PoolTimeout` / `ConnectionTimeout: connection timeout expired` | The app can't reach `postgres` over the Docker network. Codespaces: [same legacy firewall fix](#codespaces-containers-cant-reach-each-other-or-the-internet). Elsewhere: `docker compose -f infrastructure/non-prod/docker-compose.yml logs postgres` |
| `app` waits forever / `dependency failed to start: container data-onboarding-postgres is unhealthy` | `docker compose -f infrastructure/non-prod/docker-compose.yml logs postgres`. An init-script error (e.g. `$'\r': command not found` = the script was checked out with Windows line endings) means the databases weren't created. Fix it, then `down -v` (**deletes the database**) and `up -d` |
| `network data-platform was found but has incorrect label` | The ingestion repo's `bootstrap.sh` created the network first (standalone mode). Stop the ingestion stack, `docker network rm data-platform`, start this stack, then the ingestion stack |
| `password authentication failed for user "agent"` | The passwords in `.env` changed after the first start; the volume keeps the old ones. `ALTER ROLE agent PASSWORD '…'` as `postgres`, or `down -v` on a throwaway setup |
| Header pill "Repos not readable" / 404 in Settings → Repositories | The token is missing or can't read one of the repos. In Codespaces it's the preset `GITHUB_TOKEN`: set `PLATFORM_GITHUB_TOKEN` (secret, `.env` or `export`), then `up -d` |
| No login page, every tab open | `ACCOUNTS` is empty. Set it in `infrastructure/non-prod/.env` (or as a Codespaces secret), then `up -d` |
| A requester forgot their password | `docker compose -f infrastructure/non-prod/docker-compose.yml exec postgres psql -U agent -d onboarding_agent -c "DELETE FROM requesters WHERE email = 'alice@gmail.com'"`; their next sign-in sets a new one. Sessions are kept |
| `port is already allocated` | Something else uses 7860. Set `UI_PORT=7861` in `.env` and open that port instead |
