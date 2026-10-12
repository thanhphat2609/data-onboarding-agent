# playbooks/

Mỗi nguồn data một file `<source>.yaml` (tên file = mã nguồn viết thường, vd. `gsc.yaml`).

Khi thư mục này **chưa có file `.yaml` nào**, agent tự dùng playbook mẫu trong `demo/playbooks/`.
Có từ 1 file trở lên thì agent chỉ đọc thư mục này.

## Template

```yaml
source: gsc
display_name: Google Search Console
review_status: draft            # đổi thành "reviewed" sau khi team review
access_methods:
  - type: bigquery_bulk_export
    available_from: "YYYY-MM-DD"   # ngày sớm nhất có data qua cách này (null nếu không giới hạn)
    max_lookback_days: null        # giới hạn lịch sử tính từ hôm nay (null nếu không có)
    typical_lead_time_days: 5      # số ngày team thường cần để dựng pipeline
    notes: ""
current_connector: ""
existing_models: []
owner: ""
notes: ""
```

Ngày sớm nhất lấy được của một access method = `max(available_from, hôm nay - max_lookback_days)`.
Điền retention / giới hạn theo tài liệu chính thức và kinh nghiệm thực tế của team — không để agent tự đoán.
