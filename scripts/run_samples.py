"""Run sample requests (scripted conversations) through the agent and compare with expected results.

Usage:
    python scripts/run_samples.py                     # default: demo/sample_requests
    python scripts/run_samples.py sample_requests
"""
import sys
from pathlib import Path

import yaml
from langgraph.checkpoint.memory import InMemorySaver

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    return {"observed": observed, "mismatches": check(sample.get("expected") or {}, observed)}


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


def main(folder: Path) -> int:
    files = sorted(folder.glob("*.yaml"))
    if not files:
        print(f"No samples in {folder}")
        return 1
    failed = 0
    for path in files:
        sample = yaml.safe_load(path.read_text(encoding="utf-8"))
        res = run_sample(sample)
        obs = res["observed"]
        ok = not res["mismatches"]
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {path.name} — {sample.get('name', '')}")
        print(f"      turns={obs['turns']} gap={obs['gap_types']} recommended={obs['recommendation']}")
        if obs["outputs"].get("user_story"):
            print(f"      US: {obs['outputs']['user_story']}")
        for m in res["mismatches"]:
            print(f"      ✗ {m}")
    print(f"\n{len(files) - failed}/{len(files)} pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "demo" / "sample_requests"))
