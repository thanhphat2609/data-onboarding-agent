"""Minimal Ollama client. The LLM only fills in / phrases things; all branching lives in code.

If no model is configured or Ollama is unreachable, get_llm() returns None and the nodes
fall back to rule-based logic. Host/model/API key can be changed at runtime via configure()
(used by the LLM settings panel in the web UI). The API key is only needed for a remote
Ollama behind notebooks/ollama_auth_proxy.py (e.g. the Colab-hosted model).
"""
import json
import logging
import time
from functools import lru_cache

import requests

from agent import config

log = logging.getLogger(__name__)


def _headers(api_key: str | None) -> dict:
    """The Authorization header for an Ollama server behind an API key; none without a key."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class OllamaLLM:
    def __init__(self, model: str, host: str | None = None, api_key: str | None = None, timeout: int = 180):
        """A client for one model on an Ollama server (config.OLLAMA_HOST by default)."""
        self.model = model
        self.host = (host or config.OLLAMA_HOST).rstrip("/")
        self.api_key = config.OLLAMA_API_KEY if api_key is None else api_key
        self.timeout = timeout

    def chat(self, messages: list[dict], json_mode: bool = False, tools: list[dict] | None = None) -> dict:
        """One non-streaming chat call; with ``json_mode`` the answer is JSON, with ``tools`` it may call them."""
        payload = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0}}
        if json_mode:
            payload["format"] = "json"
        if tools:
            payload["tools"] = tools
        resp = requests.post(f"{self.host}/api/chat", json=payload, headers=_headers(self.api_key), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["message"]

    def complete(self, system: str, user: str) -> str:
        """The model's text answer to a system and a user message."""
        msg = self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        return msg.get("content", "").strip()

    def complete_json(self, system: str, user: str) -> dict:
        """The model's answer parsed as JSON; an empty dict when it can't be parsed."""
        msg = self.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=True)
        try:
            return json.loads(msg.get("content") or "{}")
        except json.JSONDecodeError:
            log.warning("LLM returned invalid JSON: %s", msg.get("content"))
            return {}


@lru_cache(maxsize=1)
def get_llm() -> OllamaLLM | None:
    """The configured model client, or None when no model is set (the agent then uses rules only)."""
    if not config.OLLAMA_MODEL:
        return None
    try:
        requests.get(f"{config.OLLAMA_HOST}/api/tags", headers=_headers(config.OLLAMA_API_KEY), timeout=10).raise_for_status()
    except requests.RequestException:
        log.warning("Cannot reach Ollama at %s, using rule-based fallback.", config.OLLAMA_HOST)
        return None
    return OllamaLLM(config.OLLAMA_MODEL)


def configure(host: str, model: str, api_key: str | None = None) -> None:
    """Switch host/model/key at runtime. An empty model disables the LLM (rule-based mode)."""
    config.OLLAMA_HOST = (host or config.OLLAMA_HOST).strip().rstrip("/")
    config.OLLAMA_MODEL = (model or "").strip()
    if api_key is not None:
        config.OLLAMA_API_KEY = api_key.strip()
    get_llm.cache_clear()


def list_models(host: str, api_key: str = "") -> list[str]:
    """Models already pulled on the Ollama server (raises if it is unreachable)."""
    resp = requests.get(f"{host.rstrip('/')}/api/tags", headers=_headers(api_key), timeout=15)
    resp.raise_for_status()
    return sorted(m["name"] for m in resp.json().get("models", []))


def ping(host: str, model: str, api_key: str = "") -> tuple[str, float]:
    """Send a tiny prompt; returns (reply, seconds). Raises on failure."""
    start = time.perf_counter()
    reply = OllamaLLM(model, host, api_key, timeout=120).complete("Reply in one short sentence.", "Say hello.")
    return reply, time.perf_counter() - start


def status() -> str:
    """A line saying which model is in use, or that there is none."""
    llm = get_llm()
    if llm:
        return f"LLM: `{llm.model}` @ {llm.host}"
    if config.OLLAMA_MODEL:
        return f"Rule-based (cannot reach Ollama at {config.OLLAMA_HOST})"
    return "Rule-based (no LLM configured)"


def load_prompt(name: str) -> str:
    """The text of a prompt file in ``agent/prompts``."""
    return (config.PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def safe_call(fn, *args, default=None, **kwargs):
    """Call the LLM without letting LLM errors break the flow."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM error, using fallback: %s", exc)
        return default
