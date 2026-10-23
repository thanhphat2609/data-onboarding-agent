"""Knowledge lookups over the two platform repositories (agent/repos.py): ingestion facts per system
and a search over the dbt models of the transformation repo."""
import re

from agent import repos
from agent.extraction import norm

# Bilingual (Vietnamese + English) stopwords, since requests can be written in either language.
STOPWORDS = {
    "và", "của", "cho", "các", "những", "theo", "từ", "đến", "data", "dữ", "liệu", "cần", "là", "để", "có",
    "the", "and", "for", "of", "by", "to", "a", "an", "in", "per", "with", "dùng", "một", "trong",
}


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^\w]+", norm(text)) if len(t) > 1 and t not in STOPWORDS}


def singular(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def lookup_source(system: str) -> dict:
    """What the ingestion repo knows about a source system: connections, landed tables, dbt models."""
    kb = repos.get()
    name, stype = repos.parse_source(system, kb)
    return {
        "system": name,
        "source_type": stype,
        "type_supported": bool(stype and stype in kb.templates),
        "connections": kb.connections_for(name),
        "landed_tables": kb.jobs_for(name),
        "dbt_models": [m["name"] for m in kb.models_for(name)],
    }


def search_models(query: str, system: str | None = None, top_k: int = 5) -> list[dict]:
    """dbt models related to the query. Score = share of query tokens found in the model."""
    q = {singular(t) for t in tokenize(query)}
    if not q:
        return []
    results = []
    for model in repos.get().models:
        if system and model.get("system") != system:
            continue
        haystack = {
            singular(t)
            for t in tokenize(
                " ".join([
                    model.get("name", "").replace("_", " "),
                    model.get("description", ""),
                    model.get("grain", ""),
                    " ".join(model.get("tags", [])),
                    " ".join(model.get("columns", [])).replace("_", " "),
                ])
            )
        }
        score = len(q & haystack) / len(q)
        if score > 0:
            results.append({**model, "score": round(score, 3)})
    results.sort(key=lambda m: m["score"], reverse=True)
    return results[:top_k]


# Tool schemas for testing Ollama tool calling (notebook)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_source",
            "description": "What the platform knows about a source system: is it onboarded, which tables already land in the lake, which dbt models exist.",
            "parameters": {
                "type": "object",
                "properties": {"system": {"type": "string", "description": "Source system, e.g. crm, or 'erp on postgresql'"}},
                "required": ["system"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_models",
            "description": "Search the dbt models of the transformation repo for data matching a description.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "system": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

TOOLS = {"lookup_source": lookup_source, "search_models": search_models}
