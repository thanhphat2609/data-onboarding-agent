"""Whole requests through the graph (rules only, fixture repos): feasibility per kind of work, and the outputs."""
import zipfile

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent import config, repos
from agent.workflow.evaluate import run_sample
from agent.workflow.nodes.feasibility import assess_source
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


@pytest.mark.parametrize("text, expected", [
    ("Shop on MySQL", ("shop", "mysql")),
    ("ERP on PostgreSQL", ("erp", "postgresql")),
    ("Google Search Console API", ("google search console", "rest_api")),
    ("CRM", ("crm", None)),  # a known system wins
])
def test_source_types(text, expected):
    assert repos.parse_source(text) == expected


def test_api_source_is_a_new_connection_and_still_researched():
    # The rest_api template onboards any REST API (ingestion ADR-0015), so this is no gap. The origin question and
    # the web research still run: auth and pagination are what the connection and the job need.
    runner = AgentRunner(checkpointer=InMemorySaver())
    result = run_sample(sample("dataset: Search Console clicks per page\nsource: Google Search Console API",
                               ["Google, through the Search Console API", DETAILS, DETAILS]), runner)
    obs = result["observed"]
    assert obs["status"] == "done", result
    assert not obs.get("gap_types")
    state = runner.state(runner.sessions.recent(limit=1)[0]["thread_id"])
    src = state["feasibility"]["sources"][0]
    assert src["recommendation"]["kind"] == "new_connection" and src["recommendation"]["name"] == "rest_api"
    assert state["request"]["source_origin"] == "Google, through the Search Console API"
    assert list(state["research"]) == [src["source"]]
    folder = config.ROOT / obs["outputs"]["user_story"]
    ingestion = (folder.parent / "us_2_ingestion.md").read_text()
    assert "`rest_api` source template" in ingestion and "Flink SQL over the table `landing`" in ingestion


@pytest.fixture
def empty_pipelines(tmp_path, monkeypatch):
    """The ingestion repo with an empty pipelines/ (no connection or job yet, as in a new environment)."""
    import shutil

    from tests.conftest import FIXTURES

    ingestion = tmp_path / "ingestion"
    shutil.copytree(FIXTURES / "ingestion", ingestion)
    for f in (ingestion / "pipelines").rglob("*.yaml"):
        f.unlink()
    monkeypatch.setattr(config, "INGESTION_PATH", str(ingestion))
    repos.reload()


def test_system_known_from_dbt_only_is_not_new(empty_pipelines):
    # CRM has dbt models but no connection: the existing model is still found, and CRM is not asked about or
    # researched as a new source.
    runner = AgentRunner(checkpointer=InMemorySaver())
    result = run_sample(sample("The sales team needs the current list of CRM customers with their segment for a "
                               "weekly dashboard."), runner)
    assert result["observed"]["recommendation"] == {"crm": "crm_customers_current"}
    state = runner.state(runner.sessions.recent(limit=1)[0]["thread_id"])
    assert not state["request"].get("source_origin") and not state.get("research")


def test_table_of_a_system_without_connection(empty_pipelines):
    # No connection for CRM yet: naming the source type makes it a new connection; without it, the gap says why.
    result = run_sample(sample("dataset: CRM segments table (segment id and name)\nsource: CRM on SQL Server"))
    assert result["observed"]["recommendation"] == {"crm on sql server": "sqlserver"}
    kb = repos.get()
    gap = assess_source("CRM", {"eta": None, "dataset_description": "CRM segments"}, [], None, kb)["gap"]
    assert "`crm` has dbt models but no connection in the ingestion repo" in gap["message"]
