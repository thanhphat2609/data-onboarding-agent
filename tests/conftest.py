"""Every test runs offline: the platform repos come from tests/fixtures, outputs go to a temp folder, no LLM,
no web research, and no learned-docs store unless a test sets one."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).resolve().parent / "fixtures"

from agent import config, repos  # noqa: E402
from agent.research import learned  # noqa: E402


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "")
    monkeypatch.setattr(config, "WEB_RESEARCH", False)
    monkeypatch.setattr(config, "TEAMS_WEBHOOK_URL", "")
    monkeypatch.setattr(config, "INGESTION_PATH", str(FIXTURES / "ingestion"))
    monkeypatch.setattr(config, "TRANSFORMATION_PATH", str(FIXTURES / "transformation"))
    repos.reload()
    learned.use(None)
    yield
    learned.use(None)
