"""Search the dbt models of the transformation repo for data the request may already have."""
from agent import config, repos
from agent.repos.lookup import search_models


def catalog_check(state: dict) -> dict:
    """dbt models that already match the request (score above CATALOG_MIN_SCORE): the data may exist already."""
    request = state["request"]
    query = f"{request.get('dataset_description', '')} {request.get('grain', '')}"
    kb = repos.get()
    found = []
    for source in request.get("sources", []):
        system, _ = repos.parse_source(source, kb)
        for model in search_models(query, system=system):
            if model["score"] >= config.CATALOG_MIN_SCORE:
                found.append(
                    {
                        "name": model["name"],
                        "system": system,
                        "layer": model.get("layer"),
                        "description": model.get("description", ""),
                        "grain": model.get("grain", ""),
                        "path": model.get("path", ""),
                        "score": model["score"],
                    }
                )
    return {"existing_models": found}
