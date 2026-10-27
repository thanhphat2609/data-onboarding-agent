# Prod (VM 1)

The agent and the platform's shared PostgreSQL server on VM 1, next to data-onboarding-ingestion's Airflow and Flink JobManager. **Draft until VM 1 exists.** Same CI/CD flow as data-onboarding-ingestion ([its ADR-0012](https://github.com/thanhphat2609/data-onboarding-ingestion/blob/main/docs/adr/0012-cicd-ssh-deploy.md)).

```
docker-compose.yml   postgres (databases onboarding_agent, airflow, platform) + searxng + app; creates the data-platform network
.env.example         settings; copy to .env on the VM
deploy.sh            run on VM 1 by the Deploy workflow: checkout <sha>, build, up, prune
```

## How a change reaches prod

| Stage | Trigger | What runs |
|---|---|---|
| 1. CI (`.github/workflows/ci.yml`) | Pull request or push to `main` | Ruff (errors only), compile, `import app`, Compose files, image build (not pushed) |
| 2. Deploy (`.github/workflows/deploy.yml`), approval | Someone runs **Actions → Deploy → Run workflow** on `main` | Checks the commit is on `main` with a green CI run, then VM 1: `git checkout <sha>`, `docker compose build --pull`, `up -d --wait`, prune old images and week-old build cache |

Separate from the two stages: `.github/workflows/delete-merged-branch.yml` deletes a pull request's branch once it is merged.

**Approving a deploy** = running the workflow: Actions → Deploy → Run workflow → branch `main` → optionally a commit (`sha`, default the latest `main`) and `no_cache` → Run. A commit without a green CI run is refused. A push alone deploys nothing.

PostgreSQL is not recreated by a deploy unless its settings change. Deploy this repository **before** data-onboarding-ingestion on a new VM: it creates the `data-platform` network and the database server.

## GitHub setup (Settings of this repository)

Secrets and variables are per repository: set them here **and** in data-onboarding-ingestion. Both repositories can use the same SSH key and deploy user.

### Secrets (Settings → Secrets and variables → Actions → New repository secret)

| Name | Example | What it is |
|---|---|---|
| `PROD_SSH_PRIVATE_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----`<br>`b3BlbnNzaC1rZXktdjEAAAAA...`<br>`-----END OPENSSH PRIVATE KEY-----` | Whole content of the private key file, including the BEGIN/END lines. Made once: `ssh-keygen -t ed25519 -C github-deploy -f deploy_key -N ""`; `deploy_key.pub` goes into `/home/deploy/.ssh/authorized_keys` on the VM |
| `PROD_SSH_KNOWN_HOSTS` | `20.198.10.15 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK...` | Output of `ssh-keyscan -t ed25519 20.198.10.15`; compare the fingerprint with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the VM |
| `PROD_SSH_USER` | `deploy` | Linux user on the VM, member of the `docker` group |
| `PROD_VM1_HOST` | `20.198.10.15` or `vm1.dataplatform.example.com` | Address of VM 1 that GitHub's runners can reach |

### Variables (same page → Variables tab → New repository variable)

| Name | Example | What it is |
|---|---|---|
| `PROD_DEPLOY_ENABLED` | `true` | Anything else (or unset) turns the Deploy workflow off. Leave unset until VM 1 is ready |
| `PROD_REPO_DIR` | `/opt/data-onboarding-agent` | Where the repository is cloned on the VM (this is also the default) |
| `PROD_SSH_PORT` | `22` | SSH port of the VM (default `22`) |

Variables are not secret: they show in the logs. Anything secret goes in Secrets.

### Branch protection (Settings → Rules → Rulesets, or Branches)

For `main`: require a pull request before merging, and require the status checks `Python (syntax, imports)` and `Compose files and image build`.

## VM setup (once)

```bash
sudo adduser --disabled-password deploy && sudo usermod -aG docker deploy
sudo mkdir -p /opt/data-onboarding-agent && sudo chown deploy: /opt/data-onboarding-agent
sudo -u deploy git clone https://github.com/thanhphat2609/data-onboarding-agent.git /opt/data-onboarding-agent
cd /opt/data-onboarding-agent && sudo -u deploy cp infrastructure/prod/.env.example infrastructure/prod/.env
# fill in infrastructure/prod/.env, then the first start:
sudo -u deploy docker compose -f infrastructure/prod/docker-compose.yml up -d --build
```

For a private repository, clone with a read-only **deploy key** (repository Settings → Deploy keys) instead of HTTPS. Application secrets (`ACCOUNTS`, database passwords (one per role, see [POSTGRESQL.md → Roles and passwords](../../docs/POSTGRESQL.md#roles-and-passwords)), `PLATFORM_GITHUB_TOKEN`, and `SEARXNG_SECRET`, any random string such as the output of `openssl rand -hex 32`) stay in `.env` on the VM, never in GitHub.
