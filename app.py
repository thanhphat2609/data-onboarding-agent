"""Gradio web UI for the Data Onboarding Agent.

    python app.py            # local: http://127.0.0.1:7860
    python app.py --share    # temporary public link (Colab / team demo)
    python app.py --host 0.0.0.0   # GitHub Codespaces / containers, see infrastructure/README.md

Login (agent/auth.py): set ACCOUNTS (or ACCOUNTS_FILE) to require one, e.g. only the Data Team's account. Data Team
accounts (DATA_TEAM) see every tab and every session. Any other email is a requester: it self-registers on its first
sign-in and sees only Request and its own Sessions.

Tabs:
- Request: chat + a step tracker, a live "Your request" card, the review panel (Approve / Request changes)
  and the finished User Story with download buttons. One chat session = one thread_id.
- Sessions: reopen a recent session (e.g. after a Colab disconnect) from the list or by thread_id.
- Data Team review: approve requests or ask for changes.
- Settings: switch the Ollama host/model/API key at runtime (empty model = rule-based), e.g. a model hosted on
  Colab behind notebooks/ollama_auth_proxy.py; see what was read from the ingestion and transformation repos, and reload them.
- Debug: raw agent state.
"""
import argparse

from agent.ui import launch

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="create a temporary public link (Colab)")
    parser.add_argument("--host", help="interface to bind, e.g. 0.0.0.0 in Codespaces/containers (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    launch(share=args.share, server_name=args.host, server_port=args.port)
