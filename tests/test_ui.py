"""The web UI builds, and a first message runs through its handler (no server, no browser)."""
from langgraph.checkpoint.memory import InMemorySaver

from agent.ui import build_ui, handlers
from agent.workflow.runner import AgentRunner


def test_ui_builds():
    assert build_ui() is not None


def test_first_message_reaches_the_details_step(monkeypatch):
    monkeypatch.setattr(handlers, "runner", AgentRunner(checkpointer=InMemorySaver()))
    message = "The sales team needs the current list of CRM customers with their segment for a weekly dashboard."
    updates = list(handlers.on_send(message, "", [], "", None))
    thread_id, chat = updates[-1][0], updates[-1][1]
    assert thread_id
    assert chat[0]["content"] == message
    assert handlers.runner.state(thread_id)["request"]["sources"] == ["crm"]
