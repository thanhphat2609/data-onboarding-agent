"""Send one test card to the Teams Workflows webhook, to check the channel setup before a real run.

Usage:
    python scripts/test_teams_webhook.py                 # uses TEAMS_WEBHOOK_URL
    python scripts/test_teams_webhook.py "<webhook url>"
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.integrations.teams import _adaptive_card, post_card  # noqa: E402


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("TEAMS_WEBHOOK_URL", "")
    if not url:
        print("No webhook URL: pass it as an argument or set TEAMS_WEBHOOK_URL.")
        return 1
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
    sys.exit(main())
