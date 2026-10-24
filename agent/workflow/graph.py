"""Build the graph and checkpointer.

    intake ⇄ ask_user          (ask until all fields are filled / gaps are resolved)
    intake → notify → catalog_check → feasibility
    feasibility ─gap→ intake
    feasibility → investigate_source → approval ─edit→ intake   (web research only for sources the platform can't onboard yet)
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
    summary,
)
from agent.state import AgentState


def route_intake(state: dict) -> str:
    if state.get("pending_question"):
        return "ask_user"
    return "catalog_check" if state.get("thread_ref") else "notify"


def route_feasibility(state: dict) -> str:
    return "intake" if state.get("gap") else "investigate_source"


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
    g.add_node("approval", approval)
    g.add_node("draft_us", draft_us)
    g.add_node("summary", summary)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", route_intake, ["ask_user", "notify", "catalog_check"])
    g.add_edge("ask_user", "intake")
    g.add_edge("notify", "catalog_check")
    g.add_edge("catalog_check", "feasibility")
    g.add_conditional_edges("feasibility", route_feasibility, ["intake", "investigate_source"])
    g.add_edge("investigate_source", "approval")
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

    # gssencmode=disable: libpq otherwise tries Kerberos first, whose own DNS lookups hang the connection
    # when the container's upstream DNS doesn't answer (seen in GitHub Codespaces).
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
