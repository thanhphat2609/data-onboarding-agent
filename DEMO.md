# Phase 5 – Team demo runbook

About 20 minutes. Goal: show the 3 things the prototype must prove (see `PLAN.md`), then collect feedback on the User Stories.

## Before the demo
1. **Model** (optional): host it on Colab (README → Step 1). Without it the agent runs rule-based. That is fine for the flow, but the questions and User Story text are plainer.
2. **Knowledge**: sync the real dbt catalog (📦 dbt catalog) and add whatever real playbooks exist to `playbooks/`. Anything still coming from `demo/` is flagged "DEMO data" in the output; say so out loud.
3. **Teams**: create a channel workflow *"Post to a channel when a webhook request is received"*, then:
   ```powershell
   .venv\Scripts\python scripts/test_teams_webhook.py "<webhook url>"   # check a test card shows up
   $env:TEAMS_WEBHOOK_URL = "<webhook url>"
   ```
   If a post fails during the demo, the flow keeps going and the message is saved to `outputs/<request_id>/teams_messages.jsonl` (with `webhook_error`).
4. **Real requests**: put 3–5 past requests in `sample_requests/` (copy `_template.yaml`), then run
   `.venv\Scripts\python scripts/run_samples.py sample_requests`. Read `outputs/eval/<run>/report.md` before the demo so you know where the agent goes wrong.
5. Start the app: `.venv\Scripts\python app.py`.

## Script
| # | Show | Point to make |
|---|---|---|
| 1 | New chat with a vague request (e.g. sample 01 text) | Asks only for missing fields, at most 3 per turn, done in ≤ 5 turns |
| 2 | Teams channel | "New data request" card arrives right after intake |
| 3 | Request with a date range further back than the source allows (sample 02) | Detects the gap, cites the playbook, offers an alternative start date |
| 4 | Request for data already in a dbt model | Recommends the existing model before any new ingestion |
| 4b | Request for a source with no playbook (e.g. TikTok Ads), reply `ok` | Agent reads the source's public docs and lists questions for the Data Team; findings are marked unverified |
| 5 | Approval: click **Edit** with a comment, then **Approve** | A human approves before anything is drafted; edits re-run feasibility |
| 6 | `outputs/<request_id>/user_story.md` + summary card in Teams | Ask the team: is this usable as is, with minor edits, or not? |
| 7 | `report.md` / `mistakes.csv` from the real requests | Where the agent disagreed with what the team actually did |

## Collect
- A rating per User Story (fill in the *Reviewer rating* column in `report.md`). Target: "usable, minor edits".
- Notes in the `reviewer_notes` column of `mistakes.csv`: was the agent wrong, or was the playbook/catalog missing something?
- Missing or incorrect playbook content → issue for the playbook owner.
