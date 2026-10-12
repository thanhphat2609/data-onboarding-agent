# data-onboarding-agent

An AI agent that turns data requests into ready-to-build work: it gathers requirements from users step by step, checks existing data and source feasibility (availability, date range, ETA), notifies the data team on Teams, and drafts user stories with a pipeline proposal — with human approval at every key step.

Kế hoạch chi tiết: xem `PLAN.md` (bản plan prototype).

---

## Trạng thái các phase

> Cập nhật: 2026-10-12. ✅ xong · 🟡 có code, chưa chạy/kiểm chứng ở môi trường thật · ⬜ chưa làm

### Phase 0 – Setup
- ✅ Repo + cấu trúc thư mục
- 🟡 Notebook [notebooks/prototype.ipynb](notebooks/prototype.ipynb): mount Drive, cài Ollama, pull model, test chat — **đã viết, chưa chạy trên Colab**
- 🟡 Test model gọi tool (`lookup_playbook`, `search_catalog`) — cell có sẵn trong notebook, chưa chạy
- ⬜ Chọn model 7B vs 14B — cần chạy cell so sánh trên Colab T4

### Phase 1 – Intake ✅
- ✅ `state.py` + schema request (7 field bắt buộc)
- ✅ Node `intake`: hỏi field còn thiếu (tối đa 3 field/lượt), validate date range, ETA sau hôm nay, tần suất hợp lệ
- ✅ Web UI Gradio ([app.py](app.py)), mỗi phiên = 1 `thread_id`, có nút Duyệt / Sửa, tiếp tục phiên cũ bằng `thread_id`, panel **LLM settings** để chọn host/model/API key ngay trên app (gọi được model host trên Colab)
- ✅ Checkpointer `SqliteSaver`, đã test "restart rồi chạy tiếp" ở local (tạo runner mới trên cùng file `.db`). 🟡 Chưa test với file `.db` trên Google Drive.

### Phase 2 – Knowledge
- 🟡 Playbook: mới có **playbook DEMO** cho GA4 và AppsFlyer trong `demo/playbooks/`. ⬜ Team viết playbook thật cho 7 nguồn vào `playbooks/` (GSC đang làm riêng).
- ✅ Sync catalog dbt từ **GitHub (token)**, thư mục dbt project local, hoặc `manifest.json` — trên web UI (📦 dbt catalog) hoặc [scripts/export_dbt_catalog.py](scripts/export_dbt_catalog.py). Đã test với repo public `dbt-labs/jaffle_shop`. ⬜ Chưa sync repo dbt thật của team — đang dùng catalog DEMO.
- ✅ Tool `lookup_playbook(source)` và `search_catalog(query)` ([agent/knowledge.py](agent/knowledge.py))

### Phase 3 – Feasibility ✅
- ✅ Node `catalog_check`: tìm model dbt liên quan theo từng nguồn
- ✅ Node `feasibility`: so date range yêu cầu với `available_from` / `max_lookback_days` của từng access method, cảnh báo ETA gấp theo `typical_lead_time_days`
- ✅ Có gap (date range / nguồn chưa có playbook) → quay về `intake` hỏi user chấp nhận hoặc đổi phương án
- ✅ Đề xuất hướng lấy data: ưu tiên model có sẵn → các access method trong playbook

### Phase 4 – Approval + Output ✅
- ✅ Approval dừng chờ người duyệt (dùng `interrupt()` trong node — tương đương `interrupt_before=["approval"]` nhưng nhận được dữ liệu Duyệt/Sửa khi resume). Sửa → quay về intake cập nhật request → kiểm tra khả thi lại.
- ✅ Node `draft_us`: User Story theo template (title, user story, mô tả, nguồn & khả thi, pipeline đề xuất, acceptance criteria, rủi ro, nguồn thông tin)
- ✅ Node `summary`: tin tổng hợp cuối
- ✅ Output ghi vào `outputs/<request_id>/`: `request.json`, `feasibility.json`, `user_story.md`, `summary.md`

### Phase 5 – Teams + Demo
- 🟡 Gửi tin qua Teams Workflows webhook (notify + summary, Adaptive Card) — có code, **chưa test với webhook thật**. Không đặt `TEAMS_WEBHOOK_URL` thì mock: ghi `outputs/<request_id>/teams_messages.jsonl`.
- 🟡 5 kịch bản request **DEMO** trong `demo/sample_requests/` (5/5 pass). ⬜ Cần 3–5 request thật cũ (cùng format YAML, đặt vào thư mục riêng, vd. `sample_requests/`).
- ⬜ So output của agent với cách team đã xử lý thật, ghi lại chỗ sai
- ⬜ Demo cho team

### Việc tiếp theo
1. Chạy notebook trên Colab: test tool calling, chọn model, host model cho web app trên máy (bước 4).
2. Sync catalog từ repo dbt thật (📦 dbt catalog); team viết playbook thật vào `playbooks/`.
3. Viết request thật cũ theo format trong `demo/sample_requests/`, chạy `python scripts/run_samples.py <thư mục>`.
4. Gắn webhook Teams thật.

---

## Kiến trúc

```
intake ⇄ ask_user   (hỏi đến khi đủ field / xử lý xong gap)
  │
  ▼
notify ─▶ catalog_check ─▶ feasibility ──gap──▶ intake
                               │
                               ▼
                           approval ──Sửa──▶ intake
                               │ Duyệt
                               ▼
                           draft_us ─▶ summary ─▶ END
```

- **Logic rẽ nhánh và đánh giá khả thi nằm hoàn toàn trong code.** LLM chỉ trích field từ câu trả lời tự do, diễn đạt câu hỏi và viết title/description cho User Story.
- **LLM là tùy chọn**: không đặt `OLLAMA_MODEL` (hoặc Ollama không chạy) thì agent dùng parser rule-based. Test và demo local chạy được mà không cần GPU.
- Mọi đề xuất trong User Story đều ghi rõ lấy từ playbook/catalog nào.

## Cấu trúc repo

```
data-onboarding-agent/
├── app.py                     # Web UI (Gradio)
├── notebooks/prototype.ipynb  # Colab: Ollama, test tool calling, host model qua tunnel
├── agent/
│   ├── config.py              # đường dẫn + biến môi trường
│   ├── state.py               # TypedDict state + schema request
│   ├── extraction.py          # trích field (rule-based) + validate
│   ├── knowledge.py           # lookup_playbook, search_catalog
│   ├── llm.py                 # client Ollama (tùy chọn, hỗ trợ API key)
│   ├── catalog_sync.py        # build catalog từ GitHub / local / manifest
│   ├── graph.py               # build graph, checkpointer SQLite
│   ├── runner.py              # API start/reply cho UI và test
│   ├── nodes/                 # mỗi node một file
│   ├── prompts/               # prompt cho từng bước (.md)
│   └── integrations/teams.py  # Teams webhook (hoặc mock)
├── playbooks/                 # playbook THẬT (đang trống, xem playbooks/README.md)
├── catalog/                   # catalog dbt THẬT (đang trống)
├── demo/                      # ⚠️ DỮ LIỆU MẪU — xoá cả thư mục khi đã có data thật
│   ├── playbooks/             #   ga4.yaml, appsflyer.yaml
│   ├── catalog/               #   dbt_models.json
│   └── sample_requests/       #   5 kịch bản hội thoại + kết quả kỳ vọng
├── scripts/
│   ├── export_dbt_catalog.py  # sync catalog bằng dòng lệnh
│   ├── ollama_auth_proxy.py   # proxy API key trước Ollama (chạy trên Colab)
│   └── run_samples.py         # chạy request mẫu và so với kỳ vọng
└── outputs/                   # kết quả theo request_id (gitignored)
```

### Data thật và data demo
Agent ưu tiên `playbooks/` và `catalog/dbt_models.json`. Chỉ khi chúng trống thì mới dùng `demo/`, và lúc đó mọi kết quả khả thi đều có cảnh báo "Đang chạy với DEMO data". Có thể trỏ đường dẫn khác bằng `PLAYBOOK_DIR` và `CATALOG_PATH`.

Khi chuyển code sang repo của công ty: xoá thư mục `demo/`.

## Chạy local

```bash
python -m venv .venv
.venv/Scripts/activate          # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

python app.py                   # Web UI tại http://127.0.0.1:7860  (--share để có link public)
python scripts/run_samples.py   # chạy 5 kịch bản demo
```

Trên Colab: mở [notebooks/prototype.ipynb](notebooks/prototype.ipynb).

## Mô hình chạy: Colab host model, web app chạy trên máy bạn

```
 Máy bạn                                         Google Colab (GPU T4)
┌──────────────────────────────┐   HTTPS +    ┌─────────────────────────────────────┐
│ python app.py (web UI)       │   API key    │ cloudflared tunnel                  │
│  ├─ ⚙️ LLM settings ──────────┼─────────────▶│  └─ scripts/ollama_auth_proxy.py    │
│  ├─ 📦 dbt catalog ─┐         │              │      └─ Ollama (qwen2.5 7B/14B)     │
│  └─ checkpoint, outputs      │              └─────────────────────────────────────┘
└─────────────────────┼────────┘
                      ▼ GitHub token (chỉ nằm trên máy bạn)
               GitHub repo dbt  ──▶  catalog/dbt_models.json
```

Ollama không có xác thực, nên trên Colab có thêm `scripts/ollama_auth_proxy.py` đòi API key và chỉ cho gọi các API đọc/chat (chặn pull/xoá model).

> ⚠️ Colab bản free hạn chế việc dùng runtime làm web service / truy cập không qua notebook UI. Gọi model từ máy bạn qua tunnel có thể vi phạm điều khoản và bị ngắt phiên — đọc FAQ của Colab trước khi dùng thường xuyên. Phương án dự phòng: chạy luôn web app trên Colab (cách B trong notebook), hoặc chạy Ollama trên máy có GPU / API LLM được công ty cho phép.

### Bước 1 — Host model trên Colab
Mở [notebooks/prototype.ipynb](notebooks/prototype.ipynb) trên Colab (runtime GPU T4), chạy bước 1 → 4. Bước 4 in ra:
```
Ollama host : https://xxxx.trycloudflare.com
API key     : ....
```
Giữ tab Colab mở. URL đổi mỗi lần chạy lại cell.

### Bước 2 — Mở web app trên máy bạn
```bash
python app.py        # http://127.0.0.1:7860
```
Mở **⚙️ LLM settings** ở cột phải:
- **Ollama host**: dán URL từ Colab (chạy Ollama ngay trên máy thì để `http://localhost:11434`)
- **API key**: dán key từ Colab (Ollama local thì để trống)
- **🔄 Lấy danh sách** → chọn model → **Test** → **Áp dụng**
- **Tắt LLM**: quay về rule-based. Dòng "Đang dùng" cho biết agent đang chạy bằng gì.

### Bước 3 — Sync catalog dbt từ GitHub
Mở **📦 dbt catalog**:
- **GitHub**: nhập repo `owner/name`, branch, thư mục dbt project trong repo (nếu không nằm ở gốc), và token. Bấm **Sync catalog**.
- **Local**: nhập đường dẫn thư mục dbt project, hoặc file `manifest.json`.

Agent ưu tiên `target/manifest.json` nếu có; không có thì đọc các file schema `.yml` trong `models/` (tên model, mô tả, cột, tags, `meta`). Kết quả ghi vào `catalog/dbt_models.json`, và agent dùng luôn catalog này thay cho catalog demo.

Token GitHub: nên dùng **fine-grained token chỉ có quyền `Contents: Read-only`** trên đúng repo dbt. Token chỉ dùng trong lúc sync, không ghi xuống file. Muốn khỏi nhập lại mỗi lần thì đặt biến môi trường `GITHUB_TOKEN` rồi để trống ô token.

Sync bằng dòng lệnh cũng được:
```bash
python scripts/export_dbt_catalog.py --github owner/repo --ref main --subdir dbt   # token lấy từ GITHUB_TOKEN
python scripts/export_dbt_catalog.py --project-dir ../my-dbt-project
python scripts/export_dbt_catalog.py --manifest ../my-dbt-project/target/manifest.json
```

### Cấu hình mặc định khi mở app
Cấu hình chọn trên UI sẽ mất khi tắt app. Muốn mở app là có sẵn thì đặt biến môi trường:
```powershell
$env:OLLAMA_HOST = "https://xxxx.trycloudflare.com"; $env:OLLAMA_API_KEY = "..."; $env:OLLAMA_MODEL = "qwen2.5:7b"
python app.py
```

### Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | URL Ollama local, hoặc URL tunnel từ Colab |
| `OLLAMA_API_KEY` | (trống) | Key của proxy trên Colab |
| `OLLAMA_MODEL` | (trống) | vd. `qwen2.5:7b`. Trống thì dùng rule-based |
| `GITHUB_TOKEN` | (trống) | Token đọc repo dbt, dùng khi ô token trên UI để trống |
| `CHECKPOINT_DB` | `./checkpoints.db` | |
| `OUTPUT_DIR` | `./outputs` | |
| `TEAMS_WEBHOOK_URL` | (trống) | Trống thì mock, ghi file |
| `PLAYBOOK_DIR`, `CATALOG_PATH` | `playbooks/`, `catalog/dbt_models.json` (fallback `demo/`) | |

## Đề xuất sau prototype

Theo `PLAN.md`: chuyển lên VM (Docker) + Postgres checkpointer, Teams bot để duyệt trong thread, tạo US thật trên Azure DevOps/Jira, đọc metadata Snowflake trực tiếp.

**MCP cho GitHub:** hiện catalog đọc thẳng qua GitHub API (chắc chắn hơn với model nhỏ). Khi model gọi tool ổn định (sau Phase 0), có thể gắn GitHub MCP server để agent tự đọc SQL của model khi cần trả lời chi tiết hơn (vd. model có lọc theo điều kiện X không).
