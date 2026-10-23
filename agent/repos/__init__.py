"""Knowledge from the two platform repositories, read straight from their code.

- data-onboarding-ingestion: source types that can be onboarded (`code/templates/sources/`), systems
  already onboarded (`pipelines/connections/`) and tables already landing in the lake (`pipelines/jobs/`).
- data-onboarding-transformation: dbt models that already exist (`models/**/*.yml` or a manifest).

Each repo is read from a local checkout (INGESTION_PATH / TRANSFORMATION_PATH) or from GitHub
(INGESTION_REPO / TRANSFORMATION_REPO at *_REF, token GITHUB_TOKEN). The result is cached;
reload() reads the repos again (Settings → Repositories in the UI).
"""
import logging
import re
import threading
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import yaml

from agent import config
from agent.repos import dbt_project, github

log = logging.getLogger(__name__)

INGESTION_FILES = ["code/templates/sources/*.yaml", "pipelines/connections/*.yaml", "pipelines/jobs/*.yaml"]

# How people name the source types; keys are template names in code/templates/sources/.
TYPE_ALIASES = {
    "sqlserver": ["sql server", "sqlserver", "mssql", "ms sql"],
    "postgresql": ["postgresql", "postgres"],
    "bigquery": ["bigquery", "big query"],
}
# Words around a system name in free text, e.g. "the ERP database on PostgreSQL" -> system "erp".
_FILLER = {"on", "from", "in", "our", "the", "a", "an", "database", "db", "system", "data", "server", "source", "trên", "từ", "của"}


@dataclass
class Knowledge:
    templates: dict[str, dict] = field(default_factory=dict)    # template name -> {version, file}
    connections: dict[str, dict] = field(default_factory=dict)  # connection name -> {template, system, file}
    jobs: list[dict] = field(default_factory=list)               # {name, connection, system, schema, table, path, schedule, file}
    models: list[dict] = field(default_factory=list)             # dbt models (agent/dbt_project.py)
    origin: dict[str, str] = field(default_factory=dict)         # "ingestion"/"transformation" -> where it was read from
    errors: list[str] = field(default_factory=list)

    def systems(self) -> list[str]:
        return sorted({j["system"] for j in self.jobs} | {c["system"] for c in self.connections.values()})

    def jobs_for(self, system: str) -> list[dict]:
        return [j for j in self.jobs if j["system"] == system]

    def connections_for(self, system: str) -> list[dict]:
        return [{"name": n, **c} for n, c in self.connections.items() if c["system"] == system]

    def models_for(self, system: str) -> list[dict]:
        return [m for m in self.models if m.get("system") == system]


def _read(repo: str, ref: str, local: str, patterns: list[str], subdir: str = "") -> tuple[dict[str, str], str]:
    """{path relative to the repo (or subdir): text} for files matching any pattern, and where they came from."""
    if local:
        root = Path(local) / subdir
        if not root.is_dir():
            raise FileNotFoundError(f"Local checkout not found: {root}")
        files = {
            p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for pattern in patterns for p in root.glob(pattern) if p.is_file()
        }
        return files, f"local checkout {root}"
    token = config.github_token()
    prefix = f"{subdir.strip('/')}/" if subdir.strip("/") else ""
    paths = [p for p in github.tree(repo, ref, token) if p.startswith(prefix)]
    # fnmatch's * also matches "/", so "models/**/*.yml" covers every depth.
    wanted = [p for p in paths if any(fnmatch(p.removeprefix(prefix), pt) for pt in patterns)]
    return {p.removeprefix(prefix): github.file(repo, ref, p, token) for p in wanted}, f"github.com/{repo}@{ref}"


def _yaml(text: str) -> dict:
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return doc if isinstance(doc, dict) else {}


def parse_ingestion(files: dict[str, str]) -> tuple[dict, dict, list]:
    templates, connections, jobs = {}, {}, []
    for path, text in sorted(files.items()):
        doc = _yaml(text)
        kind = doc.get("kind")
        if kind == "SourceTemplate" and doc.get("name"):
            templates[doc["name"]] = {"version": doc.get("version"), "file": path}
        elif kind == "Connection" and doc.get("name"):
            connections[doc["name"]] = {"template": str(doc.get("template", "")).split("@")[0], "file": path}
        elif kind == "IngestionJob" and doc.get("name"):
            sink_path = str(((doc.get("sink") or {}).get("params") or {}).get("path", ""))
            parts = sink_path.strip("/").split("/")
            if len(parts) != 3:
                log.warning("Skipping %s: sink path %r is not <system>/<schema>/<table>", path, sink_path)
                continue
            system, schema, table = parts
            jobs.append({
                "name": doc["name"], "connection": doc.get("connection"), "system": system, "schema": schema,
                "table": table, "path": sink_path, "schedule": doc.get("schedule"), "file": path,
            })
    # A connection's system is the system its jobs land in; without jobs, the first part of its
    # name (convention <system>-<type>-<env>, e.g. crm-sqlserver-nonprod).
    for name, conn in connections.items():
        landed = {j["system"] for j in jobs if j["connection"] == name}
        conn["system"] = sorted(landed)[0] if landed else name.split("-")[0]
    return templates, connections, jobs


def load() -> Knowledge:
    kb = Knowledge()
    try:
        files, kb.origin["ingestion"] = _read(config.INGESTION_REPO, config.INGESTION_REF, config.INGESTION_PATH, INGESTION_FILES)
        kb.templates, kb.connections, kb.jobs = parse_ingestion(files)
    except Exception as exc:  # noqa: BLE001
        kb.errors.append(f"Could not read the ingestion repo ({config.INGESTION_REPO}): {exc}")
    try:
        files, kb.origin["transformation"] = _read(
            config.TRANSFORMATION_REPO, config.TRANSFORMATION_REF, config.TRANSFORMATION_PATH,
            ["models/**/*.yml", "models/**/*.yaml", "target/manifest.json"], config.TRANSFORMATION_DBT_DIR,
        )
        kb.models = dbt_project.models_from_files(files)
    except Exception as exc:  # noqa: BLE001
        kb.errors.append(f"Could not read the transformation repo ({config.TRANSFORMATION_REPO}): {exc}")
    for err in kb.errors:
        log.warning(err)
    return kb


_lock = threading.Lock()
_kb: Knowledge | None = None


def get() -> Knowledge:
    """The cached knowledge, loaded on first use."""
    global _kb
    with _lock:
        if _kb is None:
            _kb = load()
        return _kb


def reload() -> Knowledge:
    global _kb
    with _lock:
        _kb = load()
        return _kb


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def source_type(text: str) -> str | None:
    """Source template mentioned in the text, e.g. "our ERP on Postgres" -> "postgresql"."""
    t = norm(text)
    for name, aliases in TYPE_ALIASES.items():
        if any(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", t) for a in aliases):
            return name
    return None


def parse_source(text: str, kb: Knowledge | None = None) -> tuple[str, str | None]:
    """(system, source type) of a requested source. A known system wins; otherwise the words left after
    removing the type and filler words, e.g. "erp on postgresql" -> ("erp", "postgresql")."""
    kb = kb or get()
    t = norm(text)
    for system in kb.systems():
        if re.search(rf"(?<!\w){re.escape(system)}(?!\w)", t):
            return system, source_type(t)
    stype = source_type(t)
    for alias in TYPE_ALIASES.get(stype or "", []):
        t = t.replace(alias, " ")
    words = [w for w in re.split(r"[^\w-]+", t) if w and w not in _FILLER]
    return (" ".join(words) or (stype or norm(text))), stype


def find_systems(text: str, kb: Knowledge | None = None) -> list[str]:
    """Known systems mentioned in free text."""
    t = norm(text)
    return [s for s in (kb or get()).systems() if re.search(rf"(?<!\w){re.escape(s)}(?!\w)", t)]
