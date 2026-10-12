"""Draft the User Story + pipeline proposal. Fixed template; the LLM (if any) only writes title/description."""
import json

from agent.llm import get_llm, load_prompt, safe_call
from agent.nodes.common import output_dir, rel

KIND_LABEL = {"existing_model": "Dùng model có sẵn", "ingest": "Ingestion mới"}


def _pipeline_steps(request: dict, src: dict) -> list[str]:
    source = src["source"]
    rec = src.get("recommendation")
    grain = request.get("grain", "")
    consumers = request.get("consumers", "")
    if rec is None:
        return [f"Data Team tìm hiểu nguồn `{source}` (chưa có playbook) rồi đề xuất cách lấy."]
    if rec["kind"] == "existing_model":
        return [
            f"Dùng lại model `{rec['name']}` (đã có trong catalog, data từ {rec['available_from'] or 'n/a'}).",
            f"Tạo model mart/view theo grain `{grain}` nếu model hiện tại chưa đúng grain.",
            f"Expose cho: {consumers}.",
        ]
    connector = rec.get("connector") or "connector hiện tại"
    return [
        f"Ingestion `{source}` qua `{rec['name']}` ({connector}), lịch {request.get('refresh_frequency')}.",
        f"Backfill từ {request['date_range']['start']}.",
        f"Model staging `stg_{source}__*` → mart theo grain `{grain}`.",
        "Thêm dbt test: not_null/unique trên key, freshness theo tần suất refresh.",
        f"Expose cho: {consumers}.",
    ]


def render_user_story(state: dict, title: str, description: str, extra_ac: list[str]) -> str:
    request = state["request"]
    feas = state["feasibility"]
    dr = request["date_range"]
    lines = [
        f"# {title}",
        "",
        f"**Request ID:** {state['request_id']}  ",
        f"**Teams thread:** {state.get('thread_ref', '')}  ",
        f"**Trạng thái khả thi:** {feas['overall']}"
        + ("  \n**Data đã có sẵn trong catalog:** có" if feas.get("data_already_available") else ""),
        "",
        "## User Story",
        f"Là **{request['consumers']}**, tôi cần data: _{request['dataset_description']}_ — "
        f"ở mức chi tiết **{request['grain']}**, cập nhật **{request['refresh_frequency']}**, "
        f"từ **{dr['start']}** đến **{dr['end']}**, go live trước **{request['eta']}**.",
        "",
        "## Mô tả",
        description,
        "",
        "## Nguồn & khả thi",
        "| Nguồn | Hướng đề xuất | Data có từ | Phủ date range | Nguồn thông tin |",
        "|---|---|---|---|---|",
    ]
    for src in feas["sources"]:
        rec = src.get("recommendation")
        if rec:
            lines.append(
                f"| {src['source']} | {KIND_LABEL[rec['kind']]}: `{rec['name']}` | {rec['available_from'] or 'không giới hạn đã biết'} "
                f"| {'✅' if rec['covers'] else '⚠️ không'} | {rec['ref']} |"
            )
        else:
            lines.append(f"| {src['source']} | Cần tìm hiểu | ? | ? | chưa có playbook |")

    lines += ["", "## Pipeline đề xuất"]
    for src in feas["sources"]:
        lines.append(f"**{src['source']}**")
        lines += [f"{i}. {step}" for i, step in enumerate(_pipeline_steps(request, src), 1)]
        lines.append("")

    ac = [
        f"Data có đầy đủ từ {dr['start']} đến {dr['end']} ở grain `{request['grain']}`.",
        f"Pipeline refresh {request['refresh_frequency']}, có test freshness tương ứng.",
        "Số liệu đối soát với UI của nguồn, sai lệch trong ngưỡng Data Team chấp nhận.",
        f"Go live và bàn giao cho {request['consumers']} trước {request['eta']}.",
    ] + extra_ac
    lines += ["## Acceptance Criteria"] + [f"- [ ] {c}" for c in ac]

    risks = feas.get("risks") or []
    accepted = state.get("accepted_gaps") or []
    lines += ["", "## Rủi ro"] + ([f"- {r}" for r in risks] or ["- Chưa phát hiện rủi ro."])
    if accepted:
        lines.append(f"- User đã chấp nhận: {', '.join(accepted)}.")
    if state.get("review_comment"):
        lines += ["", "## Ghi chú người duyệt", state["review_comment"]]
    lines += ["", "---", "_Draft do agent sinh. Thông tin date range lấy từ playbook/catalog ghi ở cột \"Nguồn thông tin\"._"]
    return "\n".join(lines) + "\n"


def draft_us(state: dict) -> dict:
    request = state["request"]
    desc = request["dataset_description"]
    short = desc if len(desc) <= 80 else desc[:80].rsplit(" ", 1)[0] + "…"
    title = f"[Data Request] {short}"
    description = (
        f"Yêu cầu từ {request['consumers']}: \"{desc}\". Nguồn: {', '.join(request['sources'])}. "
        f"Request được thu thập qua Data Onboarding Agent và đã được duyệt."
    )
    extra_ac: list[str] = []
    llm = get_llm()
    if llm:
        payload = json.dumps({"request": request, "feasibility": state["feasibility"]}, ensure_ascii=False)
        gen = safe_call(llm.complete_json, load_prompt("draft_us"), payload, default={}) or {}
        title = gen.get("title") or title
        description = gen.get("description") or description
        extra_ac = [str(x) for x in (gen.get("extra_acceptance_criteria") or [])][:3]

    md = render_user_story(state, title, description, extra_ac)
    out = output_dir(state)
    (out / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "feasibility.json").write_text(json.dumps(state["feasibility"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "user_story.md").write_text(md, encoding="utf-8")
    return {"outputs": {**(state.get("outputs") or {}), "title": title, "user_story": rel(out / "user_story.md")}}
