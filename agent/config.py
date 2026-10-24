"""Paths and settings, read from environment variables so the same code runs locally and on Colab."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The agent's knowledge comes from the code of the two platform repositories (agent/repos.py):
# - ingestion: source templates, onboarded connections and ingestion jobs (what lands in the lake)
# - transformation: dbt models (what is already modelled)
# Each is read from a local checkout when *_PATH is set, otherwise from GitHub at *_REF.
INGESTION_REPO = os.getenv("INGESTION_REPO", "thanhphat2609/data-onboarding-ingestion")
INGESTION_REF = os.getenv("INGESTION_REF", "main")
INGESTION_PATH = os.getenv("INGESTION_PATH", "")
TRANSFORMATION_REPO = os.getenv("TRANSFORMATION_REPO", "thanhphat2609/data-onboarding-transformation")
TRANSFORMATION_REF = os.getenv("TRANSFORMATION_REF", "main")
TRANSFORMATION_PATH = os.getenv("TRANSFORMATION_PATH", "")
# Folder of the dbt project inside the transformation repo ("" = repo root).
TRANSFORMATION_DBT_DIR = os.getenv("TRANSFORMATION_DBT_DIR", "")


# GitHub token that can read both repositories (fine-grained, Contents: Read-only). Not needed with local checkouts.
# In Codespaces GITHUB_TOKEN is preset to a token for the codespace's own repo only: export your own before starting.
def github_token() -> str:
    return os.getenv("GITHUB_TOKEN", "")


OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT / "outputs"))
PROMPT_DIR = ROOT / "agent" / "llm" / "prompts"

# Where sessions are saved (LangGraph checkpoints + the sessions table, agent/workflow/sessions.py):
# - DATABASE_URL set: PostgreSQL, e.g. postgresql://agent:<password>@postgres:5432/onboarding_agent (Docker compose)
# - otherwise SQLite at CHECKPOINT_DB. On Colab: CHECKPOINT_DB=/content/drive/MyDrive/data-onboarding-agent/checkpoints.db
DATABASE_URL = os.getenv("DATABASE_URL", "")
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", str(ROOT / "checkpoints.db"))

# LLM: leave OLLAMA_MODEL empty to run rule-based (no GPU needed). Can also be changed at runtime from the web UI.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
# API key for a remote Ollama behind notebooks/ollama_auth_proxy.py (e.g. hosted on Colab).
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# Web UI login (agent/auth.py). Accounts as "user:password" pairs, comma-separated in ACCOUNTS and/or one per line
# in ACCOUNTS_FILE (e.g. a Docker secret). No accounts = no login page, everyone sees every tab (local development).
ACCOUNTS = os.getenv("ACCOUNTS", "")
ACCOUNTS_FILE = os.getenv("ACCOUNTS_FILE", "")
# Accounts with full access (Data Team review, Settings, Debug, every session), comma-separated.
# Every other account is a requester: Request + Sessions, and only their own sessions.
DATA_TEAM = os.getenv("DATA_TEAM", "data.team@gmail.com")

# Teams Workflows webhook: leave empty to mock (messages are written to outputs/).
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

# Web research for sources the platform can't onboard yet (agent/research/). WEB_RESEARCH=0 turns it off
# (questions for the Data Team are still generated).
WEB_RESEARCH = os.getenv("WEB_RESEARCH", "1").strip().lower() not in ("0", "false", "no", "off")
RESEARCH_MAX_PAGES = int(os.getenv("RESEARCH_MAX_PAGES", "3"))

# Max fields asked per turn, to stay within the <= 5 turns target.
MAX_FIELDS_PER_QUESTION = 3
# Minimum score for a dbt model to count as relevant to a request.
CATALOG_MIN_SCORE = 0.15
