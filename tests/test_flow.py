"""Whole requests through the graph (rules only, fixture repos): feasibility per kind of work, and the outputs."""
import zipfile

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent import config
from agent.workflow.evaluate import run_sample
from agent.workflow.runner import AgentRunner

# Every detail at once, labelled. The grain names no table, so it can't change which table the request is about.
DETAILS = "date range: 2024-01-01 to now\neta: 2026-12-15\nrefresh: daily\ngrain: one row per id\nused by: Sales team, Power BI"


def sample(message: str, answers: list[str] | None = None) -> dict:
    return {"name": message, "today": "2026-10-27", "initial_message": message, "answers": answers or [DETAILS, DETAILS]}


@pytest.mark.parametrize("message, source, kind, name", [
    ("The sales team needs the current list of CRM customers with their segment for a weekly dashboard.",
     "crm", "existing_model", "crm_customers_current"),
    ("We need the CRM segments table (segment id and name) for the sales report.", "crm", "new_job", "crm-sqlserver-nonprod"),
    ("dataset: HR employees with department and hire date\nsource: HR on SQL Server", "hr on sql server", "new_connection", "sqlserver"),
])
def test_feasibility_per_kind_of_work(message, source, kind, name):
    runner = AgentRunner(checkpointer=InMemorySaver())
    result = run_sample(sample(message), runner)
    obs = result["observed"]
    assert obs["status"] == "done", result
    assert obs["recommendation"] == {source: name}
    thread_id = runner.sessions.recent(limit=1)[0]["thread_id"]
    feas = runner.state(thread_id)["feasibility"]
    assert feas["sources"][0]["recommendation"]["kind"] == kind
    assert obs["turns"] <= 5


def test_source_the_platform_cant_onboard_is_a_gap():
    # "Where does it come from?" first (a source the platform can't onboard), then the details, then "ok" to the gap.
    result = run_sample(sample("dataset: ERP orders\nsource: ERP on PostgreSQL",
                               ["internal ERP, a PostgreSQL database", DETAILS, "ok"]))
    assert result["observed"]["gap_types"] == ["unknown_source"]
    assert result["observed"]["status"] == "done"  # the requester answered "ok" and the Data Team approved


def test_outputs_after_approval():
    runner = AgentRunner(checkpointer=InMemorySaver())
    result = run_sample(sample("The sales team needs the current list of CRM customers with their segment."), runner)
    outputs = result["observed"]["outputs"]
    out = config.ROOT / outputs["user_story"]
    folder = out.parent if out.exists() else config.OUTPUT_DIR / next(p.name for p in config.OUTPUT_DIR.iterdir())
    names = {p.name for p in folder.iterdir()}
    assert {"request.json", "feasibility.json", "user_story.md", "summary.md",
            "us_1_spike.md", "us_2_ingestion.md", "us_3_transformation.md"} <= names
    bundle = next(p for p in folder.iterdir() if p.suffix == ".zip")
    members = {n.split("/")[-1] for n in zipfile.ZipFile(bundle).namelist()}
    assert members == {"user_story.md", "us_1_spike.md", "us_2_ingestion.md", "us_3_transformation.md"}
    parent = (folder / "user_story.md").read_text()
    assert "(us_1_spike.md)" in parent and "## To find out" not in parent  # links, not copies
    assert [s["title"].split("] ")[1].split(":")[0] for s in outputs["stories"]] == ["1/3 Spike", "2/3 Ingestion", "3/3 Transformation"]
