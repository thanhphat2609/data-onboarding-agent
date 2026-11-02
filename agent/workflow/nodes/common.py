"""Helpers shared by the workflow nodes: today's date, the output folder and request formatting."""

from datetime import date
from pathlib import Path

from agent import config
from agent.workflow.extraction import to_date


def get_today(state: dict) -> date:
    """The date the run treats as today: ``state['today']`` (tests, replays) or the real one."""
    return to_date(state.get("today")) or date.today()


def output_dir(state: dict) -> Path:
    """The request's output folder, created if needed."""
    path = config.OUTPUT_DIR / state["request_id"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def rel(path: Path) -> str:
    """A path relative to the repository root, for links in the outputs."""
    try:
        return path.relative_to(config.ROOT).as_posix()
    except ValueError:
        return str(path)


def format_request(request: dict) -> str:
    """The request's fields as Markdown lines."""
    dr = request.get("date_range") or {}
    return "\n".join(
        [
            f"- **Description:** {request.get('dataset_description', '')}",
            f"- **Sources:** {', '.join(request.get('sources', []))}",
            f"- **Date range:** {dr.get('start', '?')} → {dr.get('end', '?')}",
            f"- **ETA:** {request.get('eta', '')}",
            f"- **Refresh:** {request.get('refresh_frequency', '')}",
            f"- **Grain:** {request.get('grain', '')}",
            f"- **Consumers:** {request.get('consumers', '')}",
        ]
    )
