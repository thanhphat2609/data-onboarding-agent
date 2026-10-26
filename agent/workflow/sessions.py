"""Index of chat sessions, one row per thread_id, in the same database as the LangGraph checkpoints.

LangGraph keeps the state as binary blobs, so listing sessions or checking who owns one would mean loading
every thread. This table holds those facts in plain columns (queries: docs/POSTGRESQL.md). The runner keeps it
current; the checkpoints stay the source of truth for the state itself.

    created_by    login that typed the request (can be a Data Team member)
    requested_by  business owner of the request (defaults to created_by)
    reviewed_by   Data Team member who last approved / asked for changes

The same database also holds `requesters`: self-registered web UI logins with their password hash (agent/auth.py).
"""
import sqlite3
import threading
from datetime import datetime, timezone


_COLUMNS = "thread_id, request_id, created_by, requested_by, reviewed_by, review_action, status, sources, description, created_at, updated_at, reviewed_at"


def _schema(ts: str) -> list[str]:
    return [
        f"""CREATE TABLE IF NOT EXISTS sessions (
            thread_id     TEXT PRIMARY KEY,
            request_id    TEXT,
            created_by    TEXT NOT NULL DEFAULT '',
            requested_by  TEXT NOT NULL DEFAULT '',
            reviewed_by   TEXT,
            review_action TEXT,
            status        TEXT NOT NULL,
            sources       TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            created_at    {ts} NOT NULL,
            updated_at    {ts} NOT NULL,
            reviewed_at   {ts}
        )""",
        "CREATE INDEX IF NOT EXISTS ix_sessions_requested_by ON sessions (requested_by, updated_at)",
        "CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions (status, updated_at)",
        f"""CREATE TABLE IF NOT EXISTS requesters (
            email         TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            created_at    {ts} NOT NULL
        )""",
    ]


class SessionStore:
    """Backed by a sqlite3 connection or a psycopg ConnectionPool. SQL is written with `?` placeholders."""

    def __init__(self, sqlite_conn: sqlite3.Connection | None = None, pg_pool=None):
        self._sqlite, self._pg = sqlite_conn, pg_pool
        self._lock = threading.Lock()  # one sqlite3 connection is shared by Gradio's worker threads
        if self._sqlite is not None:
            self._sqlite.row_factory = sqlite3.Row
        for sql in _schema("TIMESTAMPTZ" if self._pg is not None else "TEXT"):
            self._run(sql)

    def _run(self, sql: str, params: tuple = ()) -> list[dict]:
        if self._pg is not None:
            with self._pg.connection() as conn:
                cur = conn.execute(sql.replace("?", "%s"), params)
                return [dict(r) for r in cur.fetchall()] if cur.description else []
        with self._lock:
            rows = self._sqlite.execute(sql, params).fetchall()
            self._sqlite.commit()
        return [dict(r) for r in rows]

    def _now(self, iso: str | None = None):
        """Timestamp parameter: a datetime for PostgreSQL (timestamptz), ISO text for SQLite."""
        ts = datetime.fromisoformat(iso) if iso else datetime.now(timezone.utc)
        return ts if self._pg is not None else ts.isoformat(timespec="microseconds")

    def upsert(self, thread_id: str, values: dict, status: str, at: str | None = None) -> None:
        """Insert or refresh the row from the thread's state. created_by and created_at never change."""
        request = values.get("request") or {}
        now = self._now(at)
        self._run(
            """INSERT INTO sessions (thread_id, request_id, created_by, requested_by, status, sources, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (thread_id) DO UPDATE SET
                 request_id = excluded.request_id, requested_by = excluded.requested_by, status = excluded.status,
                 sources = excluded.sources, description = excluded.description, updated_at = excluded.updated_at""",
            (
                thread_id,
                values.get("request_id"),
                values.get("created_by") or values.get("requested_by") or "",
                values.get("requested_by") or "",
                status,
                ", ".join(request.get("sources") or []),
                request.get("dataset_description") or "",
                now,
                now,
            ),
        )

    def record_review(self, thread_id: str, reviewer: str, action: str) -> None:
        self._run(
            "UPDATE sessions SET reviewed_by = ?, review_action = ?, reviewed_at = ? WHERE thread_id = ?",
            (reviewer, action, self._now(), thread_id),
        )

    def get(self, thread_id: str) -> dict | None:
        rows = self._run(f"SELECT {_COLUMNS} FROM sessions WHERE thread_id = ?", (thread_id,))
        return rows[0] if rows else None

    def recent(self, user: str | None = None, status: str | None = None, limit: int = 30) -> list[dict]:
        """Newest first. `user` = only sessions they requested or typed; `status` = one of the runner's event types (empty, question, approval, done)."""
        where, params = [], []
        if user is not None:
            where.append("(requested_by = ? OR created_by = ?)")
            params += [user, user]
        if status:
            where.append("status = ?")
            params.append(status)
        sql = f"SELECT {_COLUMNS} FROM sessions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self._run(sql + " ORDER BY updated_at DESC LIMIT ?", (*params, limit))

    def unindexed(self) -> list[str]:
        """thread_ids with checkpoints but no row yet (sessions saved before this table existed)."""
        try:
            rows = self._run(
                "SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns = '' "
                "AND thread_id NOT IN (SELECT thread_id FROM sessions)"
            )
        except Exception:  # noqa: BLE001  no checkpoints table yet (fresh database, in-memory checkpointer)
            return []
        return [r["thread_id"] for r in rows]

    # ---------- self-registered requesters (agent/auth.py) ----------

    def requester_hash(self, email: str) -> str | None:
        rows = self._run("SELECT password_hash FROM requesters WHERE email = ?", (email,))
        return rows[0]["password_hash"] if rows else None

    def register_requester(self, email: str, password_hash: str) -> str:
        """Store the hash unless the email registered meanwhile; returns the hash that is stored now."""
        self._run(
            "INSERT INTO requesters (email, password_hash, created_at) VALUES (?, ?, ?) ON CONFLICT (email) DO NOTHING",
            (email, password_hash, self._now()),
        )
        return self.requester_hash(email)
