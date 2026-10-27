"""The web UI's layout (tabs, components, event wiring) and launch()."""

import gradio as gr

from agent import auth, config
from agent.llm import client as llm
from agent.ui.handlers import (
    EXAMPLES,
    N_OUT,
    PLACEHOLDERS,
    WELCOME,
    _repos_md,
    _view,
    on_apply,
    on_approve_draft,
    on_disable,
    on_example,
    on_load,
    on_poll,
    on_refresh_models,
    on_refresh_sessions,
    on_reload_repos,
    on_resume,
    on_review_decision,
    on_review_open,
    on_review_refresh,
    on_send,
    on_test,
    runner,
)
from agent.ui.style import CSS, THEME
from agent.ui.views import _header_html, _request_html, _stepper_html


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Data Onboarding Agent") as demo:
        thread_state = gr.State("")
        header = gr.HTML(_header_html())
        account = gr.HTML()
        full = not auth.enabled()  # with a login, Data Team tabs stay hidden until on_load knows who it is

        with gr.Tabs(selected="request") as tabs:
            with gr.Tab("💬 Request", id="request"):
                with gr.Row(elem_classes="toolbar"):
                    stepper = gr.HTML(_stepper_html("describe"))
                    new_btn = gr.Button("＋ New request", size="sm", scale=0, min_width=140)
                with gr.Row(equal_height=False):
                    with gr.Column(scale=3):
                        chat = gr.Chatbot(
                            elem_id="chat", show_label=False, height="56vh", buttons=[], placeholder=WELCOME, examples=EXAMPLES
                        )
                        box = gr.Textbox(
                            show_label=False, placeholder=PLACEHOLDERS["describe"], lines=1, max_lines=8, submit_btn="Send", autofocus=True
                        )
                    with gr.Column(scale=2):
                        # Read-only for the requester: the Data Team decides in the review tab.
                        with gr.Group(visible=False, elem_classes="review-box") as waiting_box:
                            waiting_html = gr.HTML()
                        # The requester checks the draft here before it goes to the Data Team.
                        with gr.Group(visible=False, elem_classes="draft-box") as draft_box:
                            gr.Markdown("**Draft** — not sent to the Data Team yet. Approve it, or type a change in the chat.")
                            approve_draft_btn = gr.Button("✓ Approve draft", variant="primary")
                            draft_main = gr.Markdown(elem_classes="us-preview")
                            with gr.Accordion("Technical details (sources, pipeline, web research)", open=False):
                                draft_technical = gr.Markdown(elem_classes="us-preview")
                        with gr.Group(visible=False, elem_classes="result-box") as result_box:
                            result_title = gr.Markdown(elem_classes="result-title")
                            with gr.Row():
                                us_dl = gr.DownloadButton("⬇ User Stories (.zip)", variant="primary", size="sm", visible=False)
                                sum_dl = gr.DownloadButton("⬇ Summary (.md)", size="sm", visible=False)
                            with gr.Accordion("Preview User Story", open=False):
                                result_preview = gr.Markdown(elem_classes="us-preview")
                        request_card = gr.HTML(_request_html({}))
                        on_behalf = gr.Textbox(
                            label="On behalf of (Data Team, optional)",
                            placeholder="requester@company.com",
                            info="Filing a new request for someone else: they own the session and see it under Sessions.",
                            visible=full,
                        )

            with gr.Tab("🗂 Sessions", id="sessions") as sessions_tab:
                gr.Markdown("Sessions are saved automatically. Reopen one to continue where you left off, e.g. after a disconnect.")
                with gr.Row(equal_height=True):
                    session_dd = gr.Dropdown(label="Recent sessions", choices=[], scale=5)
                    refresh_sessions = gr.Button("↻ Refresh", scale=0, min_width=110)
                old_tid = gr.Textbox(label="…or paste a thread_id")
                resume_btn = gr.Button("Open session", variant="primary")
                thread_label = gr.Textbox(label="Current thread_id", interactive=False)

            with gr.Tab("🛡 Data Team review", id="review", visible=full) as review_tab:
                with gr.Column():
                    review_count = gr.Markdown()
                    with gr.Row(equal_height=True):
                        review_dd = gr.Dropdown(label="Waiting for review", choices=[], scale=5)
                        review_refresh = gr.Button("↻ Refresh", scale=0, min_width=110)
                    review_msg = gr.Markdown()
                    review_us = gr.DownloadButton("⬇ User Stories (.zip)", size="sm", visible=False)
                    with gr.Row(equal_height=False, visible=False) as review_panel:
                        with gr.Column(scale=1):
                            review_request = gr.HTML()
                        with gr.Column(scale=1):
                            with gr.Group(elem_classes="review-box"):
                                review_feas = gr.HTML()
                                review_comment = gr.Textbox(
                                    show_label=False,
                                    placeholder="Comment: what should change? e.g. change eta to 2026-12-01 (needed for Request changes)",
                                )
                                with gr.Row():
                                    approve_btn = gr.Button("✓ Approve", variant="primary")
                                    edit_btn = gr.Button("✎ Request changes")

            with gr.Tab("⚙️ Settings", id="settings", visible=full) as settings_tab:
                with gr.Row(equal_height=False):
                    with gr.Column():
                        gr.Markdown("### LLM\nRule-based works without a model; an LLM phrases questions and the User Story better.")
                        llm_status = gr.Markdown(f"**In use:** {llm.status()}")
                        host = gr.Textbox(label="Ollama host", value=config.OLLAMA_HOST, info="Local: http://localhost:11434 · Colab: URL tunnel (https://….trycloudflare.com)")
                        api_key = gr.Textbox(label="API key", type="password", value=config.OLLAMA_API_KEY, info="Only needed for the Colab-hosted model (behind the proxy)")
                        with gr.Row():
                            model = gr.Dropdown(
                                label="Model",
                                choices=[config.OLLAMA_MODEL] if config.OLLAMA_MODEL else [],
                                value=config.OLLAMA_MODEL or None,
                                allow_custom_value=True,
                                scale=3,
                            )
                            refresh_btn = gr.Button("🔄 Fetch models", scale=1)
                        with gr.Row():
                            test_btn = gr.Button("Test")
                            apply_btn = gr.Button("Apply", variant="primary")
                            disable_btn = gr.Button("Disable LLM")
                        llm_msg = gr.Markdown()
                    with gr.Column():
                        gr.Markdown(
                            "### Repositories\nThe agent reads the code of these repos to see what is already "
                            "ingested and modelled. Set `INGESTION_PATH` / `TRANSFORMATION_PATH` for local checkouts; "
                            "otherwise they are read from GitHub with `GITHUB_TOKEN`."
                        )
                        repos_md = gr.Markdown(_repos_md())
                        reload_btn = gr.Button("↻ Reload repositories", variant="primary")

            with gr.Tab("🔧 Debug", id="debug", visible=full) as debug_tab:
                gr.Markdown("Raw agent state of the current session.")
                state_json = gr.Code(language="json")

        mark = gr.State("")
        poll_timer = gr.Timer(5, active=False)

        outputs = [thread_state, chat, box, stepper, request_card, waiting_box, waiting_html, draft_box, draft_main, draft_technical,
                   result_box, result_title, result_preview, us_dl, sum_dl, state_json, mark, poll_timer]
        assert len(outputs) == N_OUT
        # The chat shows its own "thinking" bubble, so hide Gradio's progress overlay.
        busy = {"show_progress": "hidden"}
        box.submit(on_send, [box, thread_state, chat, on_behalf], outputs, **busy)
        chat.example_select(on_example, [thread_state, chat, on_behalf], outputs, **busy)
        approve_draft_btn.click(on_approve_draft, [thread_state, chat], outputs, **busy)
        poll_timer.tick(on_poll, [thread_state, chat, mark], outputs, **busy)
        new_btn.click(lambda: _view("", []), None, outputs)
        thread_state.change(lambda t: t, thread_state, thread_label)

        review_tab.select(on_review_refresh, None, [review_dd, review_count, review_panel])
        review_refresh.click(on_review_refresh, None, [review_dd, review_count, review_panel])
        review_dd.change(on_review_open, review_dd, [review_panel, review_request, review_feas, review_msg])
        decision_out = [review_msg, review_us, review_panel, review_dd, review_comment]
        approve_btn.click(on_review_decision("approve"), [review_dd, review_comment], decision_out)
        edit_btn.click(on_review_decision("edit"), [review_dd, review_comment], decision_out)

        sessions_tab.select(on_refresh_sessions, None, session_dd)
        refresh_sessions.click(on_refresh_sessions, None, session_dd)
        resume_btn.click(on_resume, [session_dd, old_tid], outputs + [tabs], **busy)

        refresh_btn.click(on_refresh_models, [host, api_key, model], [model, llm_msg])
        test_btn.click(on_test, [host, api_key, model], llm_msg)
        apply_btn.click(on_apply, [host, api_key, model], [llm_status, header])
        disable_btn.click(on_disable, host, [llm_status, header])
        reload_btn.click(on_reload_repos, None, [repos_md, header])
        demo.load(on_load, None, [account, review_tab, settings_tab, debug_tab, session_dd, on_behalf])
    return demo


def launch(**kwargs):
    """Build and launch the UI with its theme and CSS (use this from the notebook too)."""
    kwargs.setdefault("footer_links", ["gradio", "settings"])
    # Download buttons serve files from outputs/, which may live outside the working directory (OUTPUT_DIR).
    kwargs.setdefault("allowed_paths", [str(config.OUTPUT_DIR)])
    if auth.enabled():
        kwargs.setdefault("auth", lambda username, password: auth.check(username, password, runner.sessions))
        kwargs.setdefault("auth_message", auth.LOGIN_MESSAGE)
    build_ui().launch(theme=THEME, css=CSS, **kwargs)
