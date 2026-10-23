"""Paths and settings, read from environment variables so the same code runs locally and on Colab."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEMO_DIR = ROOT / "demo"


def _knowledge_path(env: str, real: Path, demo: Path) -> Path:
    """Prefer the env var, then real data; fall back to demo/ while no real data exists."""
    if os.getenv(env):
        return Path(os.environ[env])
    has_real = any(real.glob("*.yaml")) if real.suffix == "" else real.exists()
    return real if has_real else demo


PLAYBOOK_DIR = _knowledge_path("PLAYBOOK_DIR", ROOT / "playbooks", DEMO_DIR / "playbooks")
CATALOG_PATH = _knowledge_path("CATALOG_PATH", ROOT / "catalog" / "dbt_models.json", DEMO_DIR / "catalog" / "dbt_models.json")


def demo_parts() -> list[str]:
    """Which knowledge sources currently come from demo/ (re-evaluated, since catalog sync can change it)."""
    parts = []
    if PLAYBOOK_DIR.is_relative_to(DEMO_DIR):
        parts.append("playbook")
    if CATALOG_PATH.is_relative_to(DEMO_DIR):
        parts.append("catalog")
    return parts

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT / "outputs"))
PROMPT_DIR = ROOT / "agent" / "prompts"

# On Colab: CHECKPOINT_DB=/content/drive/MyDrive/data-onboarding-agent/checkpoints.db
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", str(ROOT / "checkpoints.db"))

# LLM: leave OLLAMA_MODEL empty to run rule-based (no GPU needed). Can also be changed at runtime from the web UI.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
# API key for a remote Ollama behind scripts/ollama_auth_proxy.py (e.g. hosted on Colab).
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# GitHub token for the dbt catalog sync. DBT_GITHUB_TOKEN wins: in Codespaces GITHUB_TOKEN is preset to a token
# that can only read the codespace's own repo, and secrets there can't be named GITHUB_*.
def dbt_github_token() -> str:
    return os.getenv("DBT_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN", "")

# Key for the "Data Team review" tab of the web UI (approve / request changes). Empty = tab open to everyone.
# A soft gate so requesters don't approve their own requests; the app itself has no login.
REVIEWER_KEY = os.getenv("REVIEWER_KEY", "")

# Teams Workflows webhook: leave empty to mock (messages are written to outputs/).
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL", "")

# Web research for sources without a playbook (agent/research.py). WEB_RESEARCH=0 turns it off
# (questions for the Data Team are still generated). doc_links.yaml lists known doc URLs per source.
WEB_RESEARCH = os.getenv("WEB_RESEARCH", "1").strip().lower() not in ("0", "false", "no", "off")
DOC_LINKS_PATH = Path(os.getenv("DOC_LINKS_PATH", ROOT / "doc_links.yaml"))
RESEARCH_MAX_PAGES = int(os.getenv("RESEARCH_MAX_PAGES", "3"))

# Max fields asked per turn, to stay within the <= 5 turns target.
MAX_FIELDS_PER_QUESTION = 3
# Minimum score for a dbt model to count as relevant to a request.
CATALOG_MIN_SCORE = 0.15
