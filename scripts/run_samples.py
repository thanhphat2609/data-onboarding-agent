"""Run sample requests (scripted conversations) through the agent and compare with expected results.

Usage:
    python scripts/run_samples.py                     # default: demo/sample_requests
    python scripts/run_samples.py sample_requests
    python scripts/run_samples.py sample_requests --web   # also run web research for sources without a playbook

Samples with a `team_handling` block (how the Data Team actually handled the request) are also
compared with the agent's result. Every run writes outputs/eval/<timestamp>/report.md and
mistakes.csv (one row per difference, with an empty column for the reviewer's notes).
Files starting with `_` (e.g. `_template.yaml`) are skipped.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

import yaml
from langgraph.checkpoint.memory import InMemorySaver

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import config  # noqa: E402
from agent.runner import AgentRunner  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def run_sample(sample: dict, runner: AgentRunner | None = None) -> dict:
    """Run one sample; return what was observed and the list of mismatches."""
    runner = runner or AgentRunner(checkpointer=InMemorySaver())
    answers = list(sample.get("answers") or [])
    decisions = list(sample.get("approval") or [{"action": "approve"}])
    gap_types: list[str] = []

    thread_id, event = runner.start(sample["initial_message"], today=sample.get("today"))
    for _ in range(30):  # guard against infinite loops
        if event["type"] == "question":
            st = runner.state(thread_id)
            if st.get("asked", {}).get("kind") == "gap":
                gap_types += [g["type"] for g in st["gap"]]
            if not answers:
                break
            event = runner.reply(thread_id, answers.pop(0))
        elif event["type"] == "approval":
            if not decisions:
                break
            event = runner.reply(thread_id, decisions.pop(0))
        else:
            break

    st = runner.state(thread_id)
    feas = st.get("feasibility") or {}
    observed = {
        "status": event["type"],
        "turns": st.get("intake_turns", 0),
        "gap_types": sorted(set(gap_types)),
        "data_already_available": feas.get("data_already_available"),
        "recommendation": {
            s["source"]: s["recommendation"]["name"] for s in feas.get("sources", []) if s.get("recommendation")
        },
        "request": st.get("request", {}),
        "outputs": st.get("outputs", {}),
    }
    return {
        "observed": observed,
        "mismatches": check(sample.get("expected") or {}, observed),
        "team_diffs": compare_team(sample.get("team_handling") or {}, observed),
    }


def check(expected: dict, obs: dict) -> list[str]:
    errs = []
    if obs["status"] != "done":
        errs.append(f"flow did not finish (stuck at: {obs['status']})")
    if "max_turns" in expected and obs["turns"] > expected["max_turns"]:
        errs.append(f"asked {obs['turns']} turns > {expected['max_turns']}")
    if "gap_types" in expected and sorted(expected["gap_types"]) != obs["gap_types"]:
        errs.append(f"gap {obs['gap_types']} != expected {sorted(expected['gap_types'])}")
    if "data_already_available" in expected and expected["data_already_available"] != obs["data_already_available"]:
        errs.append(f"data_already_available={obs['data_already_available']}")
    for src, name in (expected.get("recommendation") or {}).items():
        if obs["recommendation"].get(src) != name:
            errs.append(f"{src}: recommended {obs['recommendation'].get(src)} != {name}")
    if "final_date_start" in expected and obs["request"].get("date_range", {}).get("start") != expected["final_date_start"]:
        errs.append(f"date_range.start={obs['request'].get('date_range')}")
    if "final_eta" in expected and obs["request"].get("eta") != expected["final_eta"]:
        errs.append(f"eta={obs['request'].get('eta')}")
    return errs


def compare_team(team: dict, obs: dict) -> list[dict]:
    """Differences between the agent's result and how the team actually handled the request."""
    diffs = []

    def diff(check: str, agent, actual):
        if agent != actual:
            diffs.append({"check": check, "agent": agent, "team": actual})

    if "data_already_available" in team:
        diff("data_already_available", obs["data_already_available"], team["data_already_available"])
    if "gap_types" in team:
        diff("gap_types", obs["gap_types"], sorted(team["gap_types"]))
    for src, name in (team.get("recommendation") or {}).items():
        diff(f"recommendation.{src}", obs["recommendation"].get(src), name)
    if "date_start" in team:
        diff("date_range.start", obs["request"].get("date_range", {}).get("start"), team["date_start"])
    if "eta" in team:
        diff("eta", obs["request"].get("eta"), team["eta"])
    return diffs


def write_report(folder: Path, results: list[tuple[Path, dict, dict]]) -> Path:
    """Write report.md (overview + reviewer rating column) and mistakes.csv (one row per difference)."""
    out = config.OUTPUT_DIR / "eval" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    lines = [f"# Sample run — {folder}", "", f"Run at {datetime.now():%Y-%m-%d %H:%M}", ""]
    lines += ["| Sample | Expected checks | Matches team | Turns | User Story | Reviewer rating |", "|---|---|---|---|---|---|"]
    for path, sample, res in results:
        obs = res["observed"]
        if sample.get("team_handling"):
            team_cell = "✅" if not res["team_diffs"] else f"❌ {len(res['team_diffs'])} diff(s)"
        else:
            team_cell = "—"
        expected_cell = "✅" if not res["mismatches"] else "❌ " + "; ".join(res["mismatches"])
        lines.append(f"| {path.name} | {expected_cell} | {team_cell} | {obs['turns']} | {obs['outputs'].get('user_story', '')} | |")
        for m in res["mismatches"]:
            rows.append({"sample": path.name, "type": "expected", "check": m, "agent": "", "team": "", "reviewer_notes": ""})
        for d in res["team_diffs"]:
            rows.append({"sample": path.name, "type": "team", **{k: str(v) for k, v in d.items()}, "reviewer_notes": ""})
    lines += ["", "Reviewer rating: *usable as is* / *minor edits* / *major edits* / *unusable* (target: minor edits or better).", ""]
    for path, sample, res in results:
        team = sample.get("team_handling") or {}
        if not (res["team_diffs"] or team.get("notes")):
            continue
        lines += [f"## {path.name} — {sample.get('name', '')}", ""]
        for d in res["team_diffs"]:
            lines.append(f"- **{d['check']}**: agent `{d['agent']}` vs team `{d['team']}`")
        if team.get("notes"):
            lines += ["", f"Team notes: {team['notes'].strip()}"]
        lines.append("")
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    with open(out / "mistakes.csv", "w", newline="", encoding="utf-8-sig") as f:  # -sig so Excel reads UTF-8
        w = csv.DictWriter(f, fieldnames=["sample", "type", "check", "agent", "team", "reviewer_notes"])
        w.writeheader()
        w.writerows(rows)
    return out


def main(folder: Path) -> int:
    files = sorted(p for p in folder.glob("*.yaml") if not p.name.startswith("_"))
    if not files:
        print(f"No samples in {folder}")
        return 1
    failed = 0
    results = []
    for path in files:
        sample = yaml.safe_load(path.read_text(encoding="utf-8"))
        res = run_sample(sample)
        results.append((path, sample, res))
        obs = res["observed"]
        ok = not res["mismatches"]
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {path.name} — {sample.get('name', '')}")
        print(f"      turns={obs['turns']} gap={obs['gap_types']} recommended={obs['recommendation']}")
        if obs["outputs"].get("user_story"):
            print(f"      US: {obs['outputs']['user_story']}")
        for m in res["mismatches"]:
            print(f"      ✗ {m}")
        for d in res["team_diffs"]:
            print(f"      ≠ team: {d['check']} agent={d['agent']} team={d['team']}")
    report_dir = write_report(folder, results)
    print(f"\n{len(files) - failed}/{len(files)} pass")
    print(f"Report: {report_dir / 'report.md'}  ·  mistakes log: {report_dir / 'mistakes.csv'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252 and can't print ✗ / ≠
    args = [a for a in sys.argv[1:] if a != "--web"]
    # Web research is off by default so runs are repeatable and offline; --web turns it on.
    config.WEB_RESEARCH = "--web" in sys.argv
    sys.exit(main(Path(args[0]) if args else ROOT / "demo" / "sample_requests"))
