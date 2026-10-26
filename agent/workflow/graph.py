"""Build the graph and checkpointer.

    intake ⇄ ask_user          (ask until all fields are filled / gaps are resolved)
    intake → catalog_check → feasibility
    feasibility ─gap→ intake
    feasibility → investigate_source → requester_review ─change→ intake   (web research only for sources the platform can't onboard yet)
    requester_review ─approve draft→ notify (first time only) → approval ─edit→ intake
    approval ─approve→ draft_us → summary → END
"""
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agent import config
from agent.workflow.nodes import (
    approval,
    ask_user,
    catalog_check,
    draft_us,
    feasibility,
    intake,
    investigate_source,
    notify,
    requester_review,
    summary,
)
from agent.state import AgentState


def route_intake(state: dict) -> str:
    if state.get("pending_question"):
        return "ask_user"
    return "catalog_check"


def route_feasibility(state: dict) -> str:
    return "intake" if state.get("gap") else "investigate_source"


def route_requester_review(state: dict) -> str:
    """The Data Team hears about a request once the requester approved its draft (the Teams card goes out once)."""
    if not state.get("draft_approved"):
        return "intake"
    return "approval" if state.get("thread_ref") else "notify"


def route_approval(state: dict) -> str:
    return "draft_us" if state.get("approved") else "intake"


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("intake", intake)
    g.add_node("ask_user", ask_user)
    g.add_node("notify", notify)
    g.add_node("catalog_check", catalog_check)
    g.add_node("feasibility", feasibility)
    g.add_node("investigate_source", investigate_source)
    g.add_node("requester_review", requester_review)
    g.add_node("approval", approval)
    g.add_node("draft_us", draft_us)
    g.add_node("summary", summary)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", route_intake, ["ask_user", "catalog_check"])
    g.add_edge("ask_user", "intake")
    g.add_edge("catalog_check", "feasibility")
    g.add_conditional_edges("feasibility", route_feasibility, ["intake", "investigate_source"])
    g.add_edge("investigate_source", "requester_review")
    g.add_conditional_edges("requester_review", route_requester_review, ["intake", "notify", "approval"])
    g.add_edge("notify", "approval")
    g.add_conditional_edges("approval", route_approval, ["draft_us", "intake"])
    g.add_edge("draft_us", "summary")
    g.add_edge("summary", END)
    return g.compile(checkpointer=checkpointer)


def get_checkpointer(db_path: str | None = None):
    """PostgresSaver when DATABASE_URL is set (Docker), else a file-backed SqliteSaver
    (on Colab, put it on Google Drive so it survives disconnects). An explicit db_path always means SQLite."""
    if config.DATABASE_URL and not db_path:
        return _postgres_checkpointer(config.DATABASE_URL)
    path = Path(db_path or config.CHECKPOINT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def _postgres_checkpointer(url: str):
    # Imported here so SQLite-only setups (Colab, tests) don't need psycopg.
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool, PoolTimeout

    # No Kerberos on the Docker network: gssencmode=disable skips libpq's GSS attempt (and its lookups) on every connect.
    # connect_timeout: fail fast instead of hanging when the network is blocked (infrastructure/README.md#troubleshooting).
    connect = {"connect_timeout": 10, "gssencmode": "disable"}
    # Settings PostgresSaver requires: autocommit, no server-side prepared statements, rows as dicts.
    pool = ConnectionPool(
        url, min_size=1, max_size=10, open=True,
        kwargs={**connect, "autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    try:
        pool.wait(timeout=30)
    except PoolTimeout:
        # The pool only says "incomplete"; one plain connection raises the real reason
        # (wrong password, missing database, unknown host) instead.
        pool.close(timeout=1)
        psycopg.connect(url, **connect).close()
        raise
    saver = PostgresSaver(pool)
    saver.setup()  # creates / migrates the checkpoint tables
    return saver
