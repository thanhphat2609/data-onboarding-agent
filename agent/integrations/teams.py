"""Post messages to Teams via a Workflows webhook. Without TEAMS_WEBHOOK_URL, mock by writing to a file."""
import json
import logging
from datetime import datetime

import requests

from agent import config

log = logging.getLogger(__name__)


def _adaptive_card(title: str, text: str) -> dict:
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
                        {"type": "TextBlock", "text": text, "wrap": True},
                    ],
                },
            }
        ],
    }


def send_message(request_id: str, title: str, text: str) -> str:
    """Send a message and return thread_ref.

    Workflows webhooks don't return a message id, so thread_ref is the request_id put
    in the title — later messages reuse the same title so the team can follow along.
    """
    thread_ref = f"teams:{request_id}"
    card = _adaptive_card(f"[{request_id}] {title}", text)

    if config.TEAMS_WEBHOOK_URL:
        resp = requests.post(config.TEAMS_WEBHOOK_URL, json=card, timeout=15)
        resp.raise_for_status()
        return thread_ref

    out_dir = config.OUTPUT_DIR / request_id
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"sent_at": datetime.now().isoformat(timespec="seconds"), "thread_ref": thread_ref, "payload": card}
    with open(out_dir / "teams_messages.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("[MOCK TEAMS] %s — %s", title, text[:200])
    return thread_ref
