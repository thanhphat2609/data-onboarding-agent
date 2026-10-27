"""Thin API for the UI and scripts to drive the graph: one chat session = one thread_id."""
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import date

from langgraph.types import Command

from agent.research import learned
from agent.workflow.graph import build_graph, get_checkpointer
from agent.workflow.sessions import SessionStore


def _session_store(checkpointer) -> SessionStore:
    """The sessions table lives in the checkpointer's database (in memory for InMemorySaver)."""
    conn = getattr(checkpointer, "conn", None)
    if isinstance(conn, sqlite3.Connection):  # SqliteSaver: own connection to the same file
        path = conn.execute("PRAGMA database_list").fetchone()[2]
        return SessionStore(sqlite3.connect(path or ":memory:", check_same_thread=False))
    if hasattr(conn, "connection"):  # PostgresSaver on a psycopg pool
        return SessionStore(pg_pool=conn)
    return SessionStore(sqlite3.connect(":memory:", check_same_thread=False))


class AgentRunner:
    def __init__(self, checkpointer=None, db_path: str | None = None):
        checkpointer = checkpointer or get_checkpointer(db_path)
        self.graph = build_graph(checkpointer)
        self.sessions = _session_store(checkpointer)
        learned.use(self.sessions)  # research reads docs links learned from approved requests from the same database
        for thread_id in self.sessions.unindexed():  # sessions saved before the table existed
            self._index(thread_id, backfill=True)

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def new_request(
        message: str, thread_id: str | None = None, today: str | None = None, user: str = "", on_behalf_of: str = ""
    ) -> tuple[str, dict]:
        """Initial graph input for a new request typed by `user` (the web UI login), owned by `on_behalf_of`
        when the Data Team files it for someone else. Returns (thread_id, input)."""
        thread_id = thread_id or uuid.uuid4().hex[:12]
        today = today or date.today().isoformat()
        request_id = f"REQ-{today.replace('-', '')}-{thread_id[:6]}"
        return thread_id, {
            "request_id": request_id,
            "requested_by": on_behalf_of or user,
            "created_by": user,
            "today": today,
            "messages": [{"role": "user", "content": message}],
        }

    def _index(self, thread_id: str, ev: dict | None = None, backfill: bool = False) -> None:
        snapshot = self.graph.get_state(self._config(thread_id))
        if not snapshot.values:
            return
        status = (ev or self.current_event(thread_id))["type"]
        self.sessions.upsert(thread_id, snapshot.values, status, at=snapshot.created_at if backfill else None)

    def stream(self, thread_id: str, graph_input) -> Iterator[dict]:
        """Run the graph, yielding {"type": "progress", "node": name} as each node starts,
        then the resulting event (question / approval / done)."""
        for task in self.graph.stream(graph_input, self._config(thread_id), stream_mode="tasks"):
            if "result" not in task and "error" not in task:  # task start
                yield {"type": "progress", "node": task["name"]}
        ev = self.current_event(thread_id)
        self._index(thread_id, ev)
        yield ev

    def start(self, message: str, thread_id: str | None = None, today: str | None = None) -> tuple[str, dict]:
        """Start a new request. Returns (thread_id, event)."""
        thread_id, graph_input = self.new_request(message, thread_id, today)
        self.graph.invoke(graph_input, self._config(thread_id))
        ev = self.current_event(thread_id)
        self._index(thread_id, ev)
        return thread_id, ev

    def reply(self, thread_id: str, answer, reviewer: str = "") -> dict:
        """Answer the pending question (str) or the approval (dict {"action", "comment"}).
        `reviewer` = the Data Team login deciding an approval, saved in the sessions table."""
        self.graph.invoke(Command(resume=answer), self._config(thread_id))
        ev = self.current_event(thread_id)
        self._index(thread_id, ev)
        if reviewer and isinstance(answer, dict):
            self.sessions.record_review(thread_id, reviewer, answer.get("action", ""))
        if ev["type"] == "done":  # approved by the Data Team: its research links are worth keeping
            learned.learn(self.state(thread_id))
        return ev

    def current_event(self, thread_id: str) -> dict:
        """Current event of the thread: question / approval / done / empty."""
        snapshot = self.graph.get_state(self._config(thread_id))
        for task in snapshot.tasks:
            if task.interrupts:
                return dict(task.interrupts[0].value)
        if snapshot.values and not snapshot.next:
            return {"type": "done", "outputs": snapshot.values.get("outputs", {})}
        return {"type": "empty"}

    def state(self, thread_id: str) -> dict:
        return self.graph.get_state(self._config(thread_id)).values
