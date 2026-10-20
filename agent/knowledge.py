"""Knowledge lookup tools: source playbooks (YAML) and the dbt catalog (JSON)."""
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

from agent import config
from agent.extraction import norm

# Bilingual (Vietnamese + English) stopwords, since requests can be written in either language.
STOPWORDS = {
    "và", "của", "cho", "các", "những", "theo", "từ", "đến", "data", "dữ", "liệu", "cần", "là", "để", "có",
    "the", "and", "for", "of", "by", "to", "a", "an", "in", "per", "with", "dùng", "một", "trong",
}


@lru_cache(maxsize=None)
def _load_playbook_file(path: str, mtime: float) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def lookup_playbook(source: str) -> dict | None:
    """Return the source playbook (with `_file` so outputs can cite it), or None if missing."""
    # "tiktok ads" → tiktok ads.yaml or tiktok_ads.yaml (the name research drafts use)
    names = dict.fromkeys([norm(source), re.sub(r"[^\w]+", "_", norm(source)).strip("_")])
    path = next((p for n in names if (p := config.PLAYBOOK_DIR / f"{n}.yaml").exists()), None)
    if path is None:
        return None
    data = dict(_load_playbook_file(str(path), path.stat().st_mtime))
    data["_file"] = path.relative_to(config.ROOT).as_posix() if path.is_relative_to(config.ROOT) else str(path)
    return data


def list_playbooks() -> list[str]:
    return sorted(p.stem for p in config.PLAYBOOK_DIR.glob("*.yaml"))


def load_catalog() -> list[dict]:
    if not config.CATALOG_PATH.exists():
        return []
    data = json.loads(config.CATALOG_PATH.read_text(encoding="utf-8"))
    return data["models"] if isinstance(data, dict) else data


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^\w]+", norm(text)) if len(t) > 1 and t not in STOPWORDS}


def search_catalog(query: str, source: str | None = None, top_k: int = 5) -> list[dict]:
    """Find dbt models related to the query. Score = share of query tokens found in the model."""
    q = tokenize(query)
    if not q:
        return []
    results = []
    for model in load_catalog():
        if source and model.get("source") != source:
            continue
        haystack = tokenize(
            " ".join(
                [
                    model.get("name", "").replace("_", " "),
                    model.get("description", ""),
                    model.get("grain", ""),
                    " ".join(model.get("tags", [])),
                    " ".join(model.get("columns", [])).replace("_", " "),
                ]
            )
        )
        score = len(q & haystack) / len(q)
        if score > 0:
            results.append({**model, "score": round(score, 3)})
    results.sort(key=lambda m: m["score"], reverse=True)
    return results[:top_k]


# Tool schemas for testing Ollama tool calling (Phase 0 / notebook)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_playbook",
            "description": "Get the playbook of a data source: access methods, earliest available date, connector, owner.",
            "parameters": {
                "type": "object",
                "properties": {"source": {"type": "string", "description": "Lowercase source code, e.g. ga4, appsflyer"}},
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search the dbt catalog for existing models matching a description of the needed data.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "source": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

TOOLS = {"lookup_playbook": lookup_playbook, "search_catalog": search_catalog}
