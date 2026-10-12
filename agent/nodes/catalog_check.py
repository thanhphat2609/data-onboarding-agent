"""Search the dbt catalog for models that already hold the requested data."""
from agent import config
from agent.knowledge import search_catalog


def catalog_check(state: dict) -> dict:
    request = state["request"]
    query = f"{request.get('dataset_description', '')} {request.get('grain', '')}"
    found = []
    for source in request.get("sources", []):
        for model in search_catalog(query, source=source, top_k=3):
            if model["score"] >= config.CATALOG_MIN_SCORE:
                found.append(
                    {
                        "name": model["name"],
                        "source": model.get("source"),
                        "layer": model.get("layer"),
                        "description": model.get("description", ""),
                        "grain": model.get("grain", ""),
                        "data_from": model.get("data_from"),
                        "score": model["score"],
                    }
                )
    return {"existing_models": found}
