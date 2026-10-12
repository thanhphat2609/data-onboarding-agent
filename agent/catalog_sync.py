"""Build catalog/dbt_models.json from a dbt project — a manifest.json, a local project folder,
or a GitHub repo read with a token.

Without a manifest, models come from the schema .yml files under models/ (name, description,
columns, tags, meta). Extra metadata is read from each model's `meta`, e.g.:

    models:
      - name: fct_ga4__sessions_daily
        meta: {source: ga4, grain: "date x campaign", data_from: "2023-06-01"}

If meta.source is missing, it is inferred from model names like stg_<source>__xxx.
"""
import json
import re
from datetime import date
from pathlib import Path, PurePosixPath

import requests
import yaml

from agent import config

GITHUB_API = "https://api.github.com"
MAX_FILES = 1000  # guard against huge monorepos


def infer_source(name: str) -> str | None:
    m = re.match(r"^(?:stg|int|fct|dim|base)_([a-z0-9]+)__", name)
    return m.group(1) if m else None


def infer_layer(parts: list[str], fallback: str = "unknown") -> str:
    for layer in ("staging", "intermediate", "marts", "mart"):
        if layer in parts:
            return "mart" if layer.startswith("mart") else layer
    return fallback


def _model_entry(name: str, description: str, columns: list[str], tags: list[str], meta: dict, layer: str, **extra) -> dict:
    return {
        "name": name,
        "source": meta.get("source") or infer_source(name),
        "layer": layer,
        "description": description or "",
        "grain": meta.get("grain", ""),
        "columns": columns,
        "tags": tags or [],
        "data_from": meta.get("data_from"),
        "refresh": meta.get("refresh"),
        **extra,
    }


def models_from_manifest(manifest: dict) -> list[dict]:
    models = []
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "model":
            continue
        meta = {**node.get("config", {}).get("meta", {}), **node.get("meta", {})}
        models.append(
            _model_entry(
                node["name"],
                node.get("description", ""),
                list(node.get("columns", {}).keys()),
                node.get("tags", []),
                meta,
                infer_layer(node.get("fqn", []), node.get("config", {}).get("materialized", "unknown")),
                relation=node.get("relation_name"),
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
            by_name[m["name"]] = _model_entry(
                m["name"], m.get("description", ""), columns, tags, meta, infer_layer(list(PurePosixPath(path).parts)), path=path
            )
    return sorted(by_name.values(), key=lambda m: m["name"])


def _is_schema_file(path: str) -> bool:
    p = PurePosixPath(path)
    return "models" in p.parts and p.suffix in (".yml", ".yaml")


# ---------- sources ----------

def from_manifest_file(path: str | Path) -> list[dict]:
    return models_from_manifest(json.loads(Path(path).read_text(encoding="utf-8")))


def from_local_project(project_dir: str | Path) -> list[dict]:
    """Prefer target/manifest.json (after `dbt parse`); otherwise read schema .yml files."""
    root = Path(project_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Không thấy thư mục dbt project: {root}")
    manifest = root / "target" / "manifest.json"
    if manifest.exists():
        return from_manifest_file(manifest)
    files = {}
    for p in (root / "models").rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and _is_schema_file(rel):
            files[rel] = p.read_text(encoding="utf-8")
        if len(files) >= MAX_FILES:
            break
    return models_from_schema_files(files)


def _gh_get(url: str, token: str, raw: bool = False) -> requests.Response:
    headers = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 401:
        raise PermissionError("GitHub token không hợp lệ hoặc đã hết hạn.")
    if resp.status_code == 404:
        raise FileNotFoundError(f"Không tìm thấy trên GitHub (sai repo/branch, hoặc token không có quyền đọc repo): {url}")
    resp.raise_for_status()
    return resp


def from_github(repo: str, token: str, ref: str = "main", subdir: str = "") -> list[dict]:
    """Read a dbt project from GitHub. repo = "owner/name"; subdir = dbt project folder inside the repo."""
    repo = repo.strip().removeprefix("https://github.com/").strip("/")
    subdir = subdir.strip().strip("/")
    tree = _gh_get(f"{GITHUB_API}/repos/{repo}/git/trees/{ref}?recursive=1", token).json()
    paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    prefix = f"{subdir}/" if subdir else ""

    def fetch(path: str) -> str:
        return _gh_get(f"{GITHUB_API}/repos/{repo}/contents/{path}?ref={ref}", token, raw=True).text

    manifest = f"{prefix}target/manifest.json"
    if manifest in paths:
        return models_from_manifest(json.loads(fetch(manifest)))

    schema_paths = [p for p in paths if p.startswith(prefix) and _is_schema_file(p.removeprefix(prefix))][:MAX_FILES]
    if not schema_paths:
        raise FileNotFoundError(f"Không thấy file .yml nào trong `{prefix}models/` của {repo}@{ref}.")
    return models_from_schema_files({p.removeprefix(prefix): fetch(p) for p in schema_paths})


def save_catalog(models: list[dict], origin: str, out_path: Path | None = None) -> Path:
    """Write the catalog and point the agent at it (stops the demo-catalog fallback)."""
    out_path = out_path or config.ROOT / "catalog" / "dbt_models.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"generated_at": date.today().isoformat(), "origin": origin, "models": models}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config.CATALOG_PATH = out_path
    return out_path
