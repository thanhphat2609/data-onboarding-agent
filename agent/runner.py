"""Thin API for the UI and scripts to drive the graph: one chat session = one thread_id."""
import uuid
from collections.abc import Iterator
from datetime import date

from langgraph.types import Command

from agent.graph import build_graph, get_checkpointer


class AgentRunner:
    def __init__(self, checkpointer=None, db_path: str | None = None):
        self.graph = build_graph(checkpointer or get_checkpointer(db_path))

    @staticmethod
    def _config(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def new_request(message: str, thread_id: str | None = None, today: str | None = None) -> tuple[str, dict]:
        """Initial graph input for a new request. Returns (thread_id, input)."""
        thread_id = thread_id or uuid.uuid4().hex[:12]
        today = today or date.today().isoformat()
        request_id = f"REQ-{today.replace('-', '')}-{thread_id[:6]}"
        return thread_id, {"request_id": request_id, "today": today, "messages": [{"role": "user", "content": message}]}

    def stream(self, thread_id: str, graph_input) -> Iterator[dict]:
        """Run the graph, yielding {"type": "progress", "node": name} as each node starts,
        then the resulting event (question / approval / done)."""
        for task in self.graph.stream(graph_input, self._config(thread_id), stream_mode="tasks"):
            if "result" not in task and "error" not in task:  # task start
                yield {"type": "progress", "node": task["name"]}
        yield self.current_event(thread_id)

    def start(self, message: str, thread_id: str | None = None, today: str | None = None) -> tuple[str, dict]:
        """Start a new request. Returns (thread_id, event)."""
        thread_id, graph_input = self.new_request(message, thread_id, today)
        self.graph.invoke(graph_input, self._config(thread_id))
        return thread_id, self.current_event(thread_id)

    def reply(self, thread_id: str, answer) -> dict:
        """Answer the pending question (str) or the approval (dict {"action", "comment"})."""
        self.graph.invoke(Command(resume=answer), self._config(thread_id))
        return self.current_event(thread_id)

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
