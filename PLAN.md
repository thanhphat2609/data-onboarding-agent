# Data Onboarding Agent – Prototype Plan

## Tổng quan

**Repo:** `data-onboarding-agent`

**Description:**
> An AI agent that turns data requests into ready-to-build work: it gathers requirements from users step by step, checks existing data and source feasibility (availability, date range, ETA), notifies the data team on Teams, and drafts user stories with a pipeline proposal — with human approval at every key step.

**Mục tiêu prototype:** chứng minh agent làm được 3 việc:
1. Hỏi đúng và đủ thông tin từ user
2. Đánh giá khả thi đúng: data đã có chưa, lấy từ nguồn nào, date range lấy được
3. Sinh ra User Story mà Data Team dùng được

Mọi hệ thống bên ngoài (Teams, Snowflake, Azure DevOps/Jira) được **mock** ở giai đoạn này, gắn kết nối thật sau.

---

## Stack

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Môi trường | Google Colab | Chỉ dùng cho prototype |
| LLM | Ollama + model 7B–14B (vd. Qwen2.5) | Vừa GPU T4 |
| Orchestration | LangGraph | Node, rẽ nhánh, interrupt chờ duyệt |
| State | `SqliteSaver` → file `.db` trên Google Drive | Sống qua các lần Colab ngắt |
| UI | Gradio (`share=True`) | Link tạm để demo |
| Knowledge | YAML playbook + catalog dbt (export từ manifest) | Do team tự viết |
| Output | File JSON + Markdown trong `outputs/` | Tách khỏi checkpoint |

---

## Flow

```
[intake] ──đủ field──▶ [notify] ──▶ [catalog_check] ──▶ [feasibility]
   ▲                                                         │
   └───────────── có gap (date range, nguồn) ◀───────────────┤
                                                             │ không gap
                                                             ▼
                                          [approval] (interrupt, chờ người duyệt)
                                                             │
                                                             ▼
                                          [draft_us] ──▶ [summary] ──▶ END
```

| Node | Việc làm | Input → Output |
|---|---|---|
| `intake` | Hỏi user đến khi đủ field bắt buộc | Chat → `request` (JSON) |
| `notify` | Báo Data Team có request mới (mock: in/ghi file) | `request` → `thread_ref` |
| `catalog_check` | Tìm trong catalog dbt xem data đã có chưa | `request` → `existing_models` |
| `feasibility` | Tra playbook, so date range, đề xuất hướng lấy data | → `feasibility`, `gap` |
| `approval` | Dừng chờ duyệt / sửa | → `approved` |
| `draft_us` | Sinh User Story + đề xuất pipeline | → `user_story.md` |
| `summary` | Tin tổng hợp gửi lại đúng thread | → `summary.md` |

### Schema request (field bắt buộc)
- `dataset_description` – data cần là gì, dùng cho việc gì
- `sources` – nguồn (GA4, GSC, AppsFlyer, CM, GAM, DV360, DataForSEO, khác)
- `date_range` – từ ngày → đến ngày
- `eta` – ngày cần data go live
- `refresh_frequency` – daily / hourly / one-off
- `grain` – mức chi tiết (ngày, campaign, user…)
- `consumers` – ai dùng, dùng ở đâu (dashboard, report…)

---

## Cấu trúc repo

```
data-onboarding-agent/
├── notebooks/
│   └── prototype.ipynb        # setup Colab, chạy Ollama + Gradio
├── agent/
│   ├── state.py               # TypedDict state
│   ├── graph.py               # build graph, checkpointer
│   ├── nodes/                 # mỗi node một file
│   └── prompts/               # prompt cho từng node (.md)
├── playbooks/                 # 1 file YAML cho mỗi nguồn
│   ├── ga4.yaml
│   ├── gsc.yaml
│   └── ...
├── catalog/
│   └── dbt_models.json        # export từ manifest
├── outputs/                   # request JSON, user_story.md, summary.md
├── tests/
│   └── sample_requests/       # request thật cũ để chạy thử
└── README.md
```

### Mẫu playbook
```yaml
source: ga4
access_methods:
  - type: bigquery_export
    available_from: "<ngày link BQ>"   # không backfill trước ngày này
  - type: data_api
    notes: "giới hạn quota, sampling"
current_connector: "<connector team đang dùng>"
existing_models: [stg_ga4__events]
owner: "<người phụ trách>"
notes: ""
```
> Điền retention / giới hạn theo tài liệu chính thức và kinh nghiệm thực tế của team. Không để agent tự đoán.

---

## Phases

### Phase 0 – Setup (1–2 ngày)
- [ ] Tạo repo, cấu trúc thư mục như trên
- [ ] Notebook: mount Drive, cài Ollama, pull model, test chat
- [ ] Test model gọi tool đơn giản (1–2 tool giả)
- [ ] Chọn model: thử 7B và 14B, so độ ổn định khi gọi tool

### Phase 1 – Intake (3–4 ngày)
- [ ] Định nghĩa `state.py` + schema request
- [ ] Node `intake`: hỏi field còn thiếu, validate (date hợp lệ, ETA sau hôm nay…)
- [ ] Gradio chat nối vào graph, mỗi phiên = 1 `thread_id`
- [ ] Checkpointer `SqliteSaver` trên Drive, test restart Colab rồi chạy tiếp

### Phase 2 – Knowledge (2–3 ngày)
- [ ] Viết playbook cho 7 nguồn: GA4, GSC, AppsFlyer, CM, GAM, DV360, DataForSEO
- [ ] Export danh sách model dbt + mô tả từ `manifest.json` → `catalog/dbt_models.json`
- [ ] Tool `lookup_playbook(source)` và `search_catalog(query)`

### Phase 3 – Feasibility (3–4 ngày)
- [ ] Node `catalog_check`: data đã có sẵn ở model nào chưa
- [ ] Node `feasibility`: so date range yêu cầu với date range lấy được
- [ ] Rẽ nhánh khi có gap → quay về `intake` hỏi user chấp nhận phương án khác
- [ ] Đề xuất hướng lấy data: dùng model có sẵn / API / ingestion từ BQ

### Phase 4 – Approval + Output (2–3 ngày)
- [ ] `interrupt_before=["approval"]`, UI có nút Duyệt / Sửa
- [ ] Node `draft_us`: User Story theo template (title, description, acceptance criteria, nguồn, pipeline đề xuất, rủi ro)
- [ ] Node `summary`: tin tổng hợp cuối
- [ ] Ghi output vào `outputs/<request_id>/`

### Phase 5 – Teams + Demo (2 ngày)
- [ ] Gửi tin vào channel qua Teams Workflows webhook (notify + summary)
- [ ] Chạy 3–5 request thật cũ trong `tests/sample_requests/`
- [ ] So output của agent với cách team đã xử lý thật, ghi lại chỗ sai
- [ ] Demo cho team

**Tổng:** ~3 tuần làm bán thời gian.

> Trạng thái thực tế từng mục: xem README.md.

---

## Tiêu chí thành công
- Agent thu đủ field bắt buộc trong ≤ 5 lượt hỏi với request bình thường
- Phát hiện đúng gap date range ở các request test có gap
- Nhận ra đúng khi data đã có sẵn trong catalog
- Data Team đánh giá User Story "dùng được, chỉ cần sửa nhẹ"

## Ngoài phạm vi prototype
- Tạo US thật trên Azure DevOps/Jira
- Duyệt ngay trong Teams (cần bot / Graph API)
- Kết nối thật vào Snowflake
- Tự sinh code pipeline
- Deploy lên VM, auth, nhiều người dùng cùng lúc

## Rủi ro
| Rủi ro | Cách xử lý |
|---|---|
| Model nhỏ gọi tool không ổn định | Thử 14B; giữ logic rẽ nhánh trong code, LLM chỉ điền/diễn giải |
| Playbook thiếu hoặc sai | Team review playbook trước khi test; agent luôn ghi rõ nguồn thông tin |
| Colab ngắt / hết GPU | Checkpoint trên Drive; prototype không phụ thuộc chạy liên tục |
| Data nhạy cảm trên Colab | Prototype chỉ dùng metadata + request mẫu, không đưa data thật vào |

## Sau prototype
1. Chuyển lên VM (Docker), checkpointer → Postgres
2. Model: Ollama/vLLM trên VM có GPU, hoặc API LLM được công ty cho phép
3. Teams bot để duyệt trực tiếp trong thread
4. Tạo US thật trên Azure DevOps/Jira
5. Đọc metadata Snowflake trực tiếp thay cho catalog export tay
