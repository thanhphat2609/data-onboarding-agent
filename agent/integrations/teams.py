"""Post messages to Teams via a Workflows webhook. Without TEAMS_WEBHOOK_URL, mock by writing to a file.

Check a webhook before a real run (sends one test card):

    python -m agent.integrations.teams "<webhook url>"     # or set TEAMS_WEBHOOK_URL
"""
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


def post_card(webhook_url: str, card: dict) -> None:
    """POST a card to a Workflows webhook; raises on HTTP errors (Workflows answers 202 Accepted)."""
    resp = requests.post(webhook_url, json=card, timeout=15)
    resp.raise_for_status()


def _write_mock(request_id: str, thread_ref: str, card: dict, error: str | None = None) -> None:
    out_dir = config.OUTPUT_DIR / request_id
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"sent_at": datetime.now().isoformat(timespec="seconds"), "thread_ref": thread_ref, "payload": card}
    if error:
        record["webhook_error"] = error
    with open(out_dir / "teams_messages.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def send_message(request_id: str, title: str, text: str) -> str:
    """Send a message and return thread_ref.

    Workflows webhooks don't return a message id, so thread_ref is the request_id put
    in the title — later messages reuse the same title so the team can follow along.
    A failed webhook call never stops the flow: the message is written to the mock file
    with the error, so nothing is lost and the team can re-post it.
    """
    thread_ref = f"teams:{request_id}"
    card = _adaptive_card(f"[{request_id}] {title}", text)

    if config.TEAMS_WEBHOOK_URL:
        try:
            post_card(config.TEAMS_WEBHOOK_URL, card)
            return thread_ref
        except requests.RequestException as e:
            log.warning("Teams webhook failed (%s) — message saved to teams_messages.jsonl instead", e)
            _write_mock(request_id, thread_ref, card, error=str(e))
            return thread_ref

    _write_mock(request_id, thread_ref, card)
    log.info("[MOCK TEAMS] %s — %s", title, text[:200])
    return thread_ref


def _send_test_card(url: str) -> int:
    card = _adaptive_card(
        "[TEST] data-onboarding-agent",
        f"Test message sent at {datetime.now():%Y-%m-%d %H:%M:%S}.\n\n"
        "- If you can read this card in the channel, the webhook works.\n- **Bold** and lists should render.",
    )
    try:
        post_card(url, card)
    except requests.RequestException as e:
        body = getattr(e.response, "text", "")[:500] if getattr(e, "response", None) is not None else ""
        print(f"FAILED: {e}\n{body}")
        return 1
    print("Sent. Check the Teams channel — Workflows can take a few seconds to post.")
    return 0


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else config.TEAMS_WEBHOOK_URL
    if not target:
        print("No webhook URL: pass it as an argument or set TEAMS_WEBHOOK_URL.")
        sys.exit(1)
    sys.exit(_send_test_card(target))
