"""Gradio web UI for the Data Onboarding Agent.

    python app.py            # local: http://127.0.0.1:7860
    python app.py --share    # temporary public link (Colab / team demo)

One chat session = one thread_id. Enter an old thread_id to continue after a Colab disconnect.
The "LLM settings" panel switches the Ollama host/model/API key at runtime (empty model = rule-based),
e.g. to a model hosted on Colab behind scripts/ollama_auth_proxy.py.
The "dbt catalog" panel syncs the catalog from a GitHub repo (token) or a local dbt project.
"""
import argparse
import json
import os

import gradio as gr

from agent import catalog_sync, config, llm
from agent.runner import AgentRunner

runner = AgentRunner()


# ---------- chat ----------

def _approval_md(ev: dict) -> str:
    feas = ev["feasibility"]
    lines = [f"### Chờ duyệt — {ev['request_id']}", f"**Khả thi:** `{feas['overall']}`"]
    if feas.get("data_already_available"):
        lines.append("**Data đã có sẵn trong catalog** ✅")
    for src in feas["sources"]:
        rec = src.get("recommendation")
        lines.append(
            f"- **{src['source']}**: {rec['kind']} `{rec['name']}` (data từ {rec['available_from'] or 'n/a'}, nguồn: {rec['ref']})"
            if rec
            else f"- **{src['source']}**: chưa có playbook"
        )
    if feas.get("risks"):
        lines.append("\n**Rủi ro:**")
        lines += [f"- {r}" for r in feas["risks"]]
    return "\n".join(lines)


def _render(thread_id: str, ev: dict, history: list):
    """Turn an agent event into UI updates."""
    show_approval = ev["type"] == "approval"
    approval_md = _approval_md(ev) if show_approval else ""
    if ev["type"] == "question":
        history.append({"role": "assistant", "content": ev["question"]})
    elif show_approval:
        history.append({"role": "assistant", "content": "Mình đã đủ thông tin và kiểm tra khả thi xong. Bạn xem bên phải rồi bấm **Duyệt** hoặc **Sửa** nhé."})
    elif ev["type"] == "done":
        us_path = config.ROOT / ev["outputs"]["user_story"]
        us = us_path.read_text(encoding="utf-8") if us_path.exists() else ""
        history.append({"role": "assistant", "content": f"✅ Đã tạo User Story và gửi tổng hợp cho Data Team.\n\n---\n{us}"})
    values = runner.state(thread_id) if thread_id else {}
    snapshot = {k: values.get(k) for k in ("request_id", "request", "missing_fields", "gap", "existing_models", "outputs") if values.get(k)}
    return (
        thread_id,
        history,
        gr.update(visible=show_approval),
        approval_md,
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        "",
    )


def on_send(message: str, thread_id: str, history: list):
    message = (message or "").strip()
    if not message:
        return thread_id, history, gr.update(), gr.update(), gr.update(), ""
    history = history + [{"role": "user", "content": message}]
    ev = runner.current_event(thread_id) if thread_id else {"type": "empty"}
    if ev["type"] == "question":
        ev = runner.reply(thread_id, message)
    elif ev["type"] == "approval":  # typing while approval is pending = edit request
        ev = runner.reply(thread_id, {"action": "edit", "comment": message})
    else:
        thread_id, ev = runner.start(message)
    return _render(thread_id, ev, history)


def on_decision(action: str):
    def handler(comment: str, thread_id: str, history: list):
        if action == "edit" and not (comment or "").strip():
            gr.Warning("Ghi rõ cần sửa gì vào ô góp ý trước khi bấm Sửa.")
            return thread_id, history, gr.update(), gr.update(), gr.update(), comment
        label = "👍 Duyệt" if action == "approve" else f"✏️ Sửa: {comment}"
        history = history + [{"role": "user", "content": label}]
        ev = runner.reply(thread_id, {"action": action, "comment": comment or ""})
        return _render(thread_id, ev, history)

    return handler


def on_resume(old_thread_id: str):
    old_thread_id = (old_thread_id or "").strip()
    values = runner.state(old_thread_id) if old_thread_id else {}
    if not values:
        gr.Warning("Không tìm thấy phiên này trong checkpoint.")
        return "", [], gr.update(visible=False), "", "{}", ""
    history = [{"role": m["role"], "content": m["content"]} for m in values.get("messages", [])]
    return _render(old_thread_id, runner.current_event(old_thread_id), history)


# ---------- LLM settings ----------

def on_refresh_models(host: str, api_key: str, current: str):
    try:
        models = llm.list_models(host, api_key)
    except Exception as exc:  # noqa: BLE001
        if "401" in str(exc):
            return gr.update(), "❌ Sai API key."
        return gr.update(), f"❌ Không kết nối được Ollama tại `{host}`: {exc}"
    if not models:
        return gr.update(choices=[]), f"⚠️ Ollama chạy nhưng chưa có model nào. Chạy `ollama pull qwen2.5:7b` trước."
    value = current if current in models else models[0]
    return gr.update(choices=models, value=value), f"Tìm thấy {len(models)} model trên `{host}`."


def on_test(host: str, api_key: str, model: str):
    if not model:
        return "Chọn model trước khi test."
    try:
        reply, secs = llm.ping(host, model, api_key)
    except Exception as exc:  # noqa: BLE001
        return f"❌ Lỗi: {exc}"
    return f"✅ `{model}` trả lời sau {secs:.1f}s: {reply}"


def on_apply(host: str, api_key: str, model: str):
    llm.configure(host, model, api_key)
    return f"**Đang dùng:** {llm.status()}"


def on_disable(host: str):
    llm.configure(host, "")
    return f"**Đang dùng:** {llm.status()}"


# ---------- dbt catalog ----------

def _catalog_md() -> str:
    try:
        data = json.loads(config.CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "Chưa có catalog."
    origin = data.get("origin") or ("DEMO" if "catalog" in config.demo_parts() else "file")
    return f"**Catalog hiện tại:** {len(data.get('models', []))} model · nguồn `{origin}` · {data.get('generated_at', '')}"


def _demo_banner() -> str:
    demo = config.demo_parts()
    return f"> ⚠️ Đang dùng **DEMO {' + '.join(demo)}** trong `demo/`." if demo else ""


def on_sync_catalog(mode: str, repo: str, ref: str, subdir: str, token: str, local_path: str):
    try:
        if mode == "GitHub":
            if not repo.strip():
                return "Nhập repo dạng `owner/name`.", gr.update(), gr.update()
            # Token from the UI field, else from the GITHUB_TOKEN env var. Never written to disk.
            models = catalog_sync.from_github(repo, token.strip() or os.getenv("GITHUB_TOKEN", ""), ref.strip() or "main", subdir)
            origin = f"github:{repo.strip()}@{ref.strip() or 'main'}/{subdir.strip()}"
        elif local_path.strip().endswith(".json"):
            models, origin = catalog_sync.from_manifest_file(local_path.strip()), f"manifest:{local_path.strip()}"
        else:
            models, origin = catalog_sync.from_local_project(local_path.strip()), f"local:{local_path.strip()}"
    except Exception as exc:  # noqa: BLE001
        return f"❌ {exc}", gr.update(), gr.update()
    if not models:
        return "⚠️ Không tìm thấy model nào — catalog cũ được giữ nguyên.", gr.update(), gr.update()
    catalog_sync.save_catalog(models, origin)
    return f"✅ Đã sync {len(models)} model.", _catalog_md(), _demo_banner()


# ---------- layout ----------

def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Data Onboarding Agent") as demo:
        thread_state = gr.State("")
        gr.Markdown("## Data Onboarding Agent\nMô tả data bạn cần, agent sẽ hỏi thêm, kiểm tra khả thi và soạn User Story.")
        demo_banner = gr.Markdown(_demo_banner())
        with gr.Row():
            with gr.Column(scale=3):
                chat = gr.Chatbot(height=520, label="Chat")
                with gr.Row():
                    box = gr.Textbox(placeholder="Vd. Cần sessions GA4 theo campaign cho dashboard marketing…", scale=5, show_label=False)
                    send = gr.Button("Gửi", variant="primary", scale=1)
            with gr.Column(scale=2):
                with gr.Group(visible=False) as approval_box:
                    approval_md = gr.Markdown()
                    comment = gr.Textbox(label="Góp ý (bắt buộc khi Sửa)", placeholder="vd. đổi eta thành 2026-12-01")
                    with gr.Row():
                        approve_btn = gr.Button("Duyệt", variant="primary")
                        edit_btn = gr.Button("Sửa")
                with gr.Accordion("⚙️ LLM settings", open=False):
                    llm_status = gr.Markdown(f"**Đang dùng:** {llm.status()}")
                    host = gr.Textbox(label="Ollama host", value=config.OLLAMA_HOST, info="Local: http://localhost:11434 · Colab: URL tunnel (https://….trycloudflare.com)")
                    api_key = gr.Textbox(label="API key", type="password", value=config.OLLAMA_API_KEY, info="Chỉ cần khi gọi model trên Colab (qua proxy)")
                    with gr.Row():
                        model = gr.Dropdown(
                            label="Model",
                            choices=[config.OLLAMA_MODEL] if config.OLLAMA_MODEL else [],
                            value=config.OLLAMA_MODEL or None,
                            allow_custom_value=True,
                            scale=3,
                        )
                        refresh_btn = gr.Button("🔄 Lấy danh sách", scale=1)
                    with gr.Row():
                        test_btn = gr.Button("Test")
                        apply_btn = gr.Button("Áp dụng", variant="primary")
                        disable_btn = gr.Button("Tắt LLM")
                    llm_msg = gr.Markdown()
                with gr.Accordion("📦 dbt catalog", open=False):
                    catalog_md = gr.Markdown(_catalog_md())
                    cat_mode = gr.Radio(["GitHub", "Local"], value="GitHub", label="Nguồn")
                    with gr.Group():
                        gh_repo = gr.Textbox(label="Repo", placeholder="owner/dbt-repo")
                        with gr.Row():
                            gh_ref = gr.Textbox(label="Branch", value="main")
                            gh_subdir = gr.Textbox(label="Thư mục dbt project trong repo", placeholder="(để trống nếu ở gốc)")
                        gh_token = gr.Textbox(label="GitHub token", type="password", placeholder="để trống = dùng biến môi trường GITHUB_TOKEN")
                    local_path = gr.Textbox(label="Local: thư mục dbt project hoặc file manifest.json")
                    sync_btn = gr.Button("Sync catalog", variant="primary")
                    sync_msg = gr.Markdown()
                with gr.Accordion("State hiện tại", open=False):
                    state_json = gr.Code(language="json")
                with gr.Accordion("Tiếp tục phiên cũ", open=False):
                    thread_label = gr.Textbox(label="thread_id hiện tại", interactive=False)
                    old_tid = gr.Textbox(label="Nhập thread_id để chạy tiếp")
                    resume_btn = gr.Button("Tiếp tục")
                new_btn = gr.Button("Phiên mới")

        outputs = [thread_state, chat, approval_box, approval_md, state_json, box]
        send.click(on_send, [box, thread_state, chat], outputs)
        box.submit(on_send, [box, thread_state, chat], outputs)
        approve_btn.click(on_decision("approve"), [comment, thread_state, chat], outputs[:-1] + [comment])
        edit_btn.click(on_decision("edit"), [comment, thread_state, chat], outputs[:-1] + [comment])
        resume_btn.click(on_resume, [old_tid], outputs)
        new_btn.click(lambda: ("", [], gr.update(visible=False), "", "{}", ""), None, outputs)
        thread_state.change(lambda t: t, thread_state, thread_label)

        refresh_btn.click(on_refresh_models, [host, api_key, model], [model, llm_msg])
        test_btn.click(on_test, [host, api_key, model], llm_msg)
        apply_btn.click(on_apply, [host, api_key, model], llm_status)
        sync_btn.click(
            on_sync_catalog, [cat_mode, gh_repo, gh_ref, gh_subdir, gh_token, local_path], [sync_msg, catalog_md, demo_banner]
        )
        disable_btn.click(on_disable, host, llm_status)
    return demo


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true", help="create a temporary public link (Colab)")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    build_ui().launch(share=args.share, server_port=args.port)
