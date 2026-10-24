"""Web UI accounts and roles. Credentials come from ACCOUNTS / ACCOUNTS_FILE (agent/config.py), never from the repo.

- Data Team (DATA_TEAM): every tab, every session, approves requests.
- Requester (any other account): Request + Sessions, and only the sessions they started.
- No accounts configured: no login, everyone has full access (local development).
"""
import hmac
from pathlib import Path

from agent import config


def _pairs(lines) -> dict[str, str]:
    accounts = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        user, password = line.split(":", 1)  # usernames are emails; a password may contain ":"
        accounts[user.strip().lower()] = password.strip()
    return accounts


def accounts() -> dict[str, str]:
    """username -> password, from ACCOUNTS and ACCOUNTS_FILE (the file wins on duplicates)."""
    found = _pairs(config.ACCOUNTS.split(","))
    if config.ACCOUNTS_FILE:
        found |= _pairs(Path(config.ACCOUNTS_FILE).read_text(encoding="utf-8").splitlines())
    return found


def enabled() -> bool:
    return bool(accounts())


def check(username: str, password: str) -> bool:
    """Gradio's auth callback."""
    expected = accounts().get((username or "").strip().lower())
    return expected is not None and hmac.compare_digest(password.encode(), expected.encode())


def data_team() -> set[str]:
    return {u.strip().lower() for u in config.DATA_TEAM.split(",") if u.strip()}


def is_data_team(username: str | None) -> bool:
    """Full access: a Data Team account, or anyone when login is off."""
    if not enabled():
        return True
    return (username or "").strip().lower() in data_team()
