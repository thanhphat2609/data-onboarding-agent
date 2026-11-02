"""Models of a dbt project, from target/manifest.json if present, otherwise from the schema .yml files under models/.

Each model: name, system (source system it is built from), layer, description, grain, columns, tags, path.
The system comes from meta.source, else from the name (stg_<system>__<table>), else from the folder
(models/<layer>/<system>/...), which is the layout of data-onboarding-transformation.
"""
import json
import re
from pathlib import PurePosixPath

import yaml

LAYERS = ("staging", "intermediate", "marts", "mart")


def infer_system(name: str, path: str = "") -> str | None:
    """The source system of a dbt model from its name (``stg_crm__customers`` is ``crm``) or its path."""
    if m := re.match(r"^(?:stg|int|fct|dim|base)_([a-z0-9]+)__", name):
        return m.group(1)
    parts = list(PurePosixPath(path).parts)
    for i, part in enumerate(parts[:-1]):
        if part in LAYERS and i + 1 < len(parts) - 1:
            return parts[i + 1]
    return None


def infer_layer(parts: list[str], fallback: str = "unknown") -> str:
    """The dbt layer (staging, intermediate, mart...) from the folders of a path, else ``fallback``."""
    for layer in LAYERS:
        if layer in parts:
            return "mart" if layer.startswith("mart") else layer
    return fallback


def _entry(name: str, description: str, columns: list[str], tags: list[str], meta: dict, layer: str, path: str) -> dict:
    """One model as the dict the rest of the agent uses."""
    return {
        "name": name,
        "system": meta.get("source") or infer_system(name, path),
        "layer": layer,
        "description": description or "",
        "grain": meta.get("grain", ""),
        "columns": columns,
        "tags": tags or [],
        "path": path,
    }


def models_from_manifest(manifest: dict) -> list[dict]:
    """The models listed in a dbt ``manifest.json``."""
    models = []
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "model":
            continue
        meta = {**node.get("config", {}).get("meta", {}), **node.get("meta", {})}
        path = node.get("original_file_path", "")
        models.append(
            _entry(
                node["name"], node.get("description", ""), list(node.get("columns", {}).keys()), node.get("tags", []),
                meta, infer_layer(node.get("fqn", []), node.get("config", {}).get("materialized", "unknown")), path,
            )
        )
    return sorted(models, key=lambda m: m["name"])


def models_from_schema_files(files: dict[str, str]) -> list[dict]:
    """files: {posix path: yaml text}. Later definitions of the same model win."""
    by_name: dict[str, dict] = {}
    for path, text in files.items():
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        for m in doc.get("models") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            cfg = m.get("config") or {}
            meta = {**(cfg.get("meta") or {}), **(m.get("meta") or {})}
            tags = list(m.get("tags") or []) + list(cfg.get("tags") or [])
            columns = [c["name"] for c in m.get("columns") or [] if isinstance(c, dict) and c.get("name")]
            by_name[m["name"]] = _entry(
                m["name"], m.get("description", ""), columns, tags, meta, infer_layer(list(PurePosixPath(path).parts)), path
            )
    return sorted(by_name.values(), key=lambda m: m["name"])


def is_schema_file(path: str) -> bool:
    """True for a ``.yml`` or ``.yaml`` file under ``models/``."""
    p = PurePosixPath(path)
    return "models" in p.parts and p.suffix in (".yml", ".yaml")


def models_from_files(files: dict[str, str]) -> list[dict]:
    """files: {path relative to the dbt project: text}; uses target/manifest.json when it is among them."""
    if "target/manifest.json" in files:
        return models_from_manifest(json.loads(files["target/manifest.json"]))
    return models_from_schema_files({p: t for p, t in files.items() if is_schema_file(p)})
