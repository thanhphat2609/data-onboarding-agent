"""Build the graph and checkpointer.

    intake ⇄ ask_user          (ask until all fields are filled / gaps are resolved)
    intake → notify → catalog_check → feasibility
    feasibility ─gap→ intake
    feasibility → approval ─edit→ intake
    approval ─approve→ draft_us → summary → END
"""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agent import config
from agent.nodes import approval, ask_user, catalog_check, draft_us, feasibility, intake, notify, summary
from agent.state import AgentState


def route_intake(state: dict) -> str:
    if state.get("pending_question"):
        return "ask_user"
    return "catalog_check" if state.get("thread_ref") else "notify"


def route_feasibility(state: dict) -> str:
    return "intake" if state.get("gap") else "approval"


def route_approval(state: dict) -> str:
    return "draft_us" if state.get("approved") else "intake"


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("intake", intake)
    g.add_node("ask_user", ask_user)
    g.add_node("notify", notify)
    g.add_node("catalog_check", catalog_check)
    g.add_node("feasibility", feasibility)
    g.add_node("approval", approval)
    g.add_node("draft_us", draft_us)
    g.add_node("summary", summary)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", route_intake, ["ask_user", "notify", "catalog_check"])
    g.add_edge("ask_user", "intake")
    g.add_edge("notify", "catalog_check")
    g.add_edge("catalog_check", "feasibility")
    g.add_conditional_edges("feasibility", route_feasibility, ["intake", "approval"])
    g.add_conditional_edges("approval", route_approval, ["draft_us", "intake"])
    g.add_edge("draft_us", "summary")
    g.add_edge("summary", END)
    return g.compile(checkpointer=checkpointer)


def get_checkpointer(db_path: str | None = None) -> SqliteSaver:
    """File-backed SqliteSaver (on Colab, put it on Google Drive so it survives disconnects)."""
    path = Path(db_path or config.CHECKPOINT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)
