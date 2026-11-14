# Prod (VM 1)

The agent and the platform's shared PostgreSQL server on VM 1, next to data-onboarding-orchestration's Airflow and data-onboarding-ingestion's Flink JobManager. **Draft until VM 1 exists.** Same CI/CD flow as data-onboarding-ingestion ([its ADR-0012](https://github.com/thanhphat2609/data-onboarding-ingestion/blob/main/docs/adr/0012-cicd-ssh-deploy.md)).

```
docker-compose.yml   postgres (databases onboarding_agent, airflow, platform) + searxng + app; creates the data-platform network
.env.example         every prod setting; the Deploy workflow writes .env on the VM from the GitHub secrets/variables of the same name
render_env.py        used by the Deploy workflow: .env.example keys + secrets/variables -> .env (fails if a required one is missing)
deploy.sh            run on VM 1 by the Deploy workflow: checkout <sha>, build, up, prune
```

## How a change reaches prod

| Stage | Trigger | What runs |
|---|---|---|
| 1. CI (`.github/workflows/ci.yml`) | Pull request or push to `main` | Ruff (errors only), compile, `import app`, the `pytest` suite (offline), Compose files, image build (not pushed) |
| 2. Deploy (`.github/workflows/deploy.yml`), approval | Someone runs **Actions → Deploy → Run workflow** on `main` | Checks the commit is on `main` with a green CI run; writes `.env` from the secrets and variables and checks it with `docker compose config`; then VM 1: `.env` replaced, `git checkout <sha>`, `docker compose build --pull`, `up -d --wait`, prune old images and week-old build cache |

Separate from the two stages: `.github/workflows/delete-merged-branch.yml` deletes a pull request's branch once it is merged.

**Approving a deploy** = running the workflow: Actions → Deploy → Run workflow → branch `main` → optionally a commit (`sha`, default the latest `main`) and `no_cache` → Run. A commit without a green CI run is refused. A push alone deploys nothing.

PostgreSQL is not recreated by a deploy unless its settings change. Deploy this repository **first** on a new VM, then data-onboarding-ingestion, then data-onboarding-orchestration: it creates the `data-platform` network and the database server.

## GitHub setup (Settings of this repository)

**Every prod setting lives here**, nothing is edited on the VM: the Deploy workflow writes `infrastructure/prod/.env` on VM 1 on every run, one line per key of [.env.example](.env.example), from the secret or variable of the **same name** ([render_env.py](render_env.py)). It stops before touching the VM when a required secret is missing, when a password-like setting was saved as a variable, or when `docker compose config` rejects the result. To change a setting: edit it here, then run **Actions → Deploy**.

A setting you can't fill in yet: set it to **`TODO`** (secret or variable). The deploy stops while any secret or variable of this repository is still `TODO`, naming each one, so a placeholder never reaches the VM. Don't use another placeholder such as `1`: it would be deployed as a real value.

Secrets and variables are per repository: set them here, in data-onboarding-ingestion **and** in data-onboarding-orchestration. All three can use the same SSH key and deploy user. One value is shared: this repository's `POSTGRES_AIRFLOW_PASSWORD` secret = orchestration's `AIRFLOW_DB_PASSWORD` secret.

### Secrets (Settings → Secrets and variables → Actions → New repository secret)

| Name | Example | What it is |
|---|---|---|
| `PROD_SSH_PRIVATE_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----`<br>`b3BlbnNzaC1rZXktdjEAAAAA...`<br>`-----END OPENSSH PRIVATE KEY-----` | Whole content of the private key file, including the BEGIN/END lines. Made once: `ssh-keygen -t ed25519 -C github-deploy -f deploy_key -N ""`; `deploy_key.pub` goes into `/home/deploy/.ssh/authorized_keys` on the VM |
| `PROD_SSH_KNOWN_HOSTS` | `203.0.113.10 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK...` | Output of `ssh-keyscan -t ed25519 203.0.113.10`; compare the fingerprint with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the VM |
| `PROD_SSH_USER` | `deploy` | Linux user on the VM, member of the `docker` group |
| `PROD_VM1_HOST` | `203.0.113.10` or `vm1.dataplatform.example.com` | Address of VM 1 that GitHub's runners can reach |

App settings (written into `.env`; generate passwords with `openssl rand -hex 24`, URL-safe characters only):

| Name | Required | What it is |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | `postgres` superuser, admin only |
| `POSTGRES_AGENT_PASSWORD` | yes | Role `agent`, this app |
| `POSTGRES_AIRFLOW_PASSWORD` | yes | Role `airflow`; same value as orchestration's `AIRFLOW_DB_PASSWORD` |
| `POSTGRES_PLATFORM_PASSWORD` | yes | Role `platform`, ingestion's run history (empty database until its Phase 5) |
| `PLATFORM_GITHUB_TOKEN` | yes | Fine-grained token, Contents: Read-only on data-onboarding-ingestion and data-onboarding-transformation |
| `ACCOUNTS` | yes | Data Team logins, `email:password`, comma-separated |
| `SEARXNG_SECRET` | yes | Any random string (`openssl rand -hex 32`) |
| `TEAMS_WEBHOOK_URL` | no | The **Prod** channel's workflow URL (Teams → channel → Workflows → *Send webhook alerts to a channel*). Empty = messages written to `outputs/` |
| `OLLAMA_API_KEY` | no | Only for a model behind the Colab proxy |

The PostgreSQL passwords are read **only on the first start** (empty `pgdata` volume). Changing one later needs `ALTER ROLE <role> PASSWORD '…'` on the server as `postgres` first, then the new secret and a deploy; otherwise the app or Airflow can't connect. Which role is which: [postgresql.md → Roles and passwords](../../docs/postgresql.md#roles-and-passwords).

### Variables (same page → Variables tab → New repository variable)

| Name | Example | What it is |
|---|---|---|
| `PROD_DEPLOY_ENABLED` | `true` | Anything else (or unset) turns the Deploy workflow off. Leave unset until VM 1 is ready |
| `PROD_REPO_DIR` | `/opt/data-onboarding-agent` | Where the repository is cloned on the VM (this is also the default) |
| `PROD_SSH_PORT` | `22` | SSH port of the VM (default `22`) |
| `DATA_TEAM` | `data.team@company.com` | **Required.** The Data Team login(s), comma-separated; same emails as in `ACCOUNTS` |
| `OLLAMA_HOST`, `OLLAMA_MODEL` | `http://gpu-vm:11434`, `qwen2.5:14b` | The model; empty = rule-based |
| `UI_PORT`, `POSTGRES_PORT`, `WEB_RESEARCH`, `WEBSEARCH_BROWSER`, `WITH_BROWSER`, `SEARXNG_URL`, `INGESTION_REPO`/`_REF`, `TRANSFORMATION_REPO`/`_REF` | | Optional; empty = the default in [docker-compose.yml](docker-compose.yml) |

Variables are not secret: they show in the logs. Anything secret goes in Secrets.

### Branch protection (Settings → Rules → Rulesets, or Branches)

For `main`: require a pull request before merging, and require the status checks `Python (syntax, imports)` and `Compose files and image build`.

## VM setup (once)

```bash
sudo adduser --disabled-password deploy && sudo usermod -aG docker deploy
sudo mkdir -p /opt/data-onboarding-agent && sudo chown deploy: /opt/data-onboarding-agent
sudo -u deploy git clone https://github.com/thanhphat2609/data-onboarding-agent.git /opt/data-onboarding-agent
```

Then set the secrets and variables above, `PROD_DEPLOY_ENABLED=true`, and run **Actions → Deploy**: the first run writes `.env` and starts PostgreSQL (creating the databases with the passwords from GitHub), SearXNG and the app.

For a private repository, clone with a read-only **deploy key** (repository Settings → Deploy keys) instead of HTTPS. Don't edit `infrastructure/prod/.env` on the VM: the next deploy replaces it with what GitHub holds. It's written with owner-only permissions (`600`) and stays out of Git (`.gitignore`).
