# 3. Results and closing the prototype

Fill this in during the demo, then copy the outcome into [PHASES.md](../PHASES.md) (Phase 5) and the README status table.

Demo date: ____ · Presenter: ____ · Data Team reviewer: ____ · Mode: rule-based / model ____

## Happy path checklist

| # | Check | Result | Notes |
|---|---|---|---|
| A | All 7 details in ≤ 5 turns (number of turns: __) | ☐ pass ☐ fail | |
| A | Relative date ("in 4 weeks") converted and confirmed | ☐ pass ☐ fail | |
| B | Recommends the existing dbt model `crm_customers_current`, no new ingestion | ☐ pass ☐ fail | |
| B | A change to the draft gives a new draft | ☐ pass ☐ fail | |
| B | No Teams card before **✓ Approve draft**, one "New data request" card after | ☐ pass ☐ fail | |
| C | Request changes by the Data Team reaches the requester as a new draft | ☐ pass ☐ fail | |
| C | No second "New data request" card after the re-approval | ☐ pass ☐ fail | |
| D | "Request approved — User Story ready" card in Teams | ☐ pass ☐ fail | |
| D | `outputs/<request_id>/` has the 4 files, no `teams_messages.jsonl` | ☐ pass ☐ fail | |
| D | Session in PostgreSQL: `done`, `reviewed_by`, `review_action = approve` | ☐ pass ☐ fail | |
| E | Clean source name, "Where does it come from?" asked on its own | ☐ pass ☐ fail ☐ skipped | |
| E | Web research: kept results, top 5 links, marked unverified | ☐ pass ☐ fail ☐ skipped | |

## The team's rating

| User Story | Rating (usable as is / minor edits / major edits / unusable) | What they would change |
|---|---|---|
| Current CRM customers (happy path) | | |
| Google Search Console (part E) | | |

## Real past requests

3–5 requests the Data Team already handled, written as YAML in [past_requests/](past_requests/) (copy [`_template.yaml`](past_requests/_template.yaml)), then:

```bash
# docs/ is not in the image: copy the folder into the container first
docker cp docs/prototype_demo/past_requests data-onboarding-agent:/tmp/past_requests
docker exec data-onboarding-agent python -m agent.workflow.evaluate /tmp/past_requests
```

Or, with a local Python environment: `python -m agent.workflow.evaluate docs/prototype_demo/past_requests`.

It writes `outputs/eval/<timestamp>/report.md` and `mistakes.csv`. With the team, fill in the *Reviewer rating* column in `report.md` and `reviewer_notes` in `mistakes.csv`: was the agent wrong, or is something missing in a repo (a job, a connection, a model)?

| Request | Passes its checks | Matches how the team handled it | Rating |
|---|---|---|---|
| | | | |

## Decision: close the prototype?

Close it when all of these hold:

- [ ] The happy path passed end to end in Docker, with real Teams cards and PostgreSQL sessions (parts A–D above)
- [ ] ≤ 5 turns on the happy path and on the normal past requests
- [ ] Existing data recognized, and gaps (date range, unknown source) found where the past requests have them
- [ ] The team rates the User Stories **minor edits or better**
- [ ] Mistakes found are logged in `mistakes.csv` with a decision: fix now, fix after the prototype, or a repo gap

Decision: ☐ close the prototype ☐ not yet, because: ____

## What comes after (not needed to close the prototype)

1. **Which model to use** on VM 1: rule-based, a GPU host running Ollama, or an approved LLM API.
2. **VM 1**: GitHub secrets and variables ([infrastructure/prod/README.md](../../infrastructure/prod/README.md)), a prod `.env`, `PROD_DEPLOY_ENABLED=true`, then the first deploy (this repo before data-onboarding-ingestion).
3. **3 User Stories per request** (spike, ingestion, transformation): [PHASES.md → Next phase](../PHASES.md#next-phase-3-user-stories-per-request).
