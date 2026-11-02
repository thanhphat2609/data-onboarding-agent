"""On-disk cache for web research: search results and page text, kept RESEARCH_CACHE_DAYS (0 = off).

A second request for the same source reuses what the first one found: the same links every time, no new queries
for the search engines to rate-limit, and much faster. Only useful answers are kept (non-empty result lists,
pages read successfully). Lives in outputs/cache/research/, which the compose files keep across rebuilds.
"""
import hashlib
import json
import logging
import time
from pathlib import Path

from agent import config

log = logging.getLogger(__name__)


def _path(kind: str, key: str) -> Path:
    """The cache file of a key: a hash of the key under ``outputs/cache/research/<kind>``."""
    return config.OUTPUT_DIR / "cache" / "research" / kind / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")


def get(kind: str, key: str):
    """The cached value, or None when missing, expired or the cache is off."""
    if config.RESEARCH_CACHE_DAYS <= 0:
        return None
    path = _path(kind, key)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - record.get("saved_at", 0) > config.RESEARCH_CACHE_DAYS * 86400:
        return None
    return record.get("value")


def put(kind: str, key: str, value) -> None:
    """Stores a value; a full or read-only disk only costs the cache."""
    if config.RESEARCH_CACHE_DAYS <= 0:
        return
    path = _path(kind, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"key": key, "saved_at": time.time(), "value": value}, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:  # a read-only or full disk only costs the cache
        log.warning("Research cache not written (%s)", exc)
