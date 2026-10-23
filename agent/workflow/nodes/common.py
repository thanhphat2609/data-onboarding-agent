from datetime import date
from pathlib import Path

from agent import config
from agent.workflow.extraction import to_date


def get_today(state: dict) -> date:
    return to_date(state.get("today")) or date.today()


def output_dir(state: dict) -> Path:
    path = config.OUTPUT_DIR / state["request_id"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def rel(path: Path) -> str:
    try:
        return path.relative_to(config.ROOT).as_posix()
    except ValueError:
        return str(path)


def format_request(request: dict) -> str:
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
