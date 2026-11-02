"""Web UI accounts and roles. Configured credentials come from ACCOUNTS / ACCOUNTS_FILE (agent/config.py), never from the repo.

- Data Team (DATA_TEAM): every tab, every session, approves requests. Needs a password in ACCOUNTS; a Data Team
  email can never self-register.
- Requester (any other email): Request + Sessions, and only their own sessions. Either listed in ACCOUNTS, or
  self-registered: the first sign-in with an email sets its password (hashed in the `requesters` table,
  agent/workflow/sessions.py), later sign-ins must repeat it.
- No accounts configured: no login, everyone has full access (local development).
"""
import hashlib
import hmac
import re
import secrets
from pathlib import Path

from agent import config

MIN_PASSWORD = 8
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# scrypt parameters; stored with each hash so they can change later without breaking old ones.
_N, _R, _P = 2**14, 8, 1

LOGIN_MESSAGE = (
    "Data Onboarding Agent. Sign in with your email. First time here? Pick a password "
    f"(at least {MIN_PASSWORD} characters): it is saved for that email and needed next time."
)


def _pairs(lines) -> dict[str, str]:
    """``key=value`` lines as a dict."""
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
    """True when any account is configured, so the UI asks for a login."""
    return bool(accounts())


def hash_password(password: str) -> str:
    """A salted scrypt hash of the password, in the format ``verify_password`` reads."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when the password matches a stored hash; False for a malformed hash."""
    try:
        _, n, r, p, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got.hex(), digest)


def check(username: str, password: str, store=None) -> bool:
    """Gradio's auth callback. `store` = the SessionStore holding self-registered requesters (None = no self-registration)."""
    user = (username or "").strip().lower()
    password = password or ""
    configured = accounts()
    if user in configured:
        return hmac.compare_digest(password.encode(), configured[user].encode())
    if store is None or user in data_team() or not _EMAIL.match(user):
        return False
    stored = store.requester_hash(user)
    if stored is None:
        if len(password) < MIN_PASSWORD:
            return False
        stored = store.register_requester(user, hash_password(password))  # first sign-in sets the password
    return verify_password(password, stored)


def known(username: str, store=None) -> bool:
    """Has this login an account (configured or self-registered)?"""
    user = (username or "").strip().lower()
    return user in accounts() or (store is not None and store.requester_hash(user) is not None)


def data_team() -> set[str]:
    """The lowercase emails of the Data Team (config.DATA_TEAM)."""
    return {u.strip().lower() for u in config.DATA_TEAM.split(",") if u.strip()}


def is_data_team(username: str | None) -> bool:
    """Full access: a Data Team account, or anyone when login is off."""
    if not enabled():
        return True
    return (username or "").strip().lower() in data_team()
