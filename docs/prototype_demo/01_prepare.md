# 1. Prepare (before the demo)

About 45 minutes, best done an hour before so there is time to fix things. Commands assume a codespace or a Linux/macOS shell at the repo root.

## 1.1 Teams webhook (~5 min)

1. In Teams, open the demo channel → **⋯ → Workflows → "Post to a channel when a webhook request is received"**. Pick the team and channel, then copy the URL it shows.
2. Check it on its own:
   ```bash
   python -m agent.integrations.teams "<webhook url>"
   ```
   It prints `Sent.` and a card **"[TEST] data-onboarding-agent"** shows up in the channel within a few seconds. If it prints `FAILED`, recreate the workflow; the agent can't fix a bad URL.

   No local Python? Run it in the container after step 1.3: `docker exec data-onboarding-agent python -m agent.integrations.teams "<webhook url>"`.

## 1.2 Settings (~5 min)

```bash
cp -n infrastructure/non-prod/.env.example infrastructure/non-prod/.env
```

Fill in `infrastructure/non-prod/.env`:

| Variable | Value |
|---|---|
| `PLATFORM_GITHUB_TOKEN` | fine-grained token, Contents: Read-only on both platform repos. In Codespaces, set it as a **Codespaces secret** instead (the preset `GITHUB_TOKEN` wins over the file) |
| `TEAMS_WEBHOOK_URL` | the URL from 1.1 |
| `ACCOUNTS` | `data.team@gmail.com:<password>` |
| `DATA_TEAM` | `data.team@gmail.com` (the default) |
| `WEB_RESEARCH` | `1` (needed for the optional part E) |
| `OLLAMA_HOST`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` | empty = rule-based. Fill them in only if the Colab-hosted model is running ([README → Step 1](../../README.md)). **Decide before the demo**: the team rates the User Story produced by this setup |

## 1.3 Start the stack (~10 min)

```bash
git pull origin main
docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build
docker compose -f infrastructure/non-prod/docker-compose.yml ps
docker compose -f infrastructure/non-prod/docker-compose.yml logs app --tail 15
```

- `ps`: `data-onboarding-postgres`, `data-onboarding-searxng` and `data-onboarding-agent` are all `running` / `healthy`.
- `logs app`: ends with `Running on local URL`.
- A `PoolTimeout` or "DNS lookup of api.github.com failed" in a codespace: run `bash infrastructure/non-prod/codespace-network.sh`, then `docker compose -f infrastructure/non-prod/docker-compose.yml restart app` ([runbook](../../infrastructure/README.md#codespaces-containers-cant-reach-each-other-or-the-internet)).
- Open the app: `http://127.0.0.1:7860` (Codespaces: **PORTS** tab → 7860 → open in browser).

## 1.4 Check the knowledge (~5 min)

Sign in as `data.team@gmail.com` → **⚙️ Settings → Repositories**. It must list, with no error:

- system `crm` (known from its dbt models)
- dbt models `stg_crm__customers` and `crm_customers_current`
- source templates `sqlserver`, `postgresql`, `mysql`, `rest_api`
- connections and jobs: none, unless the ingestion demo's files were merged to its `main`. Since 2026-10-30 the ingestion repo's `pipelines/` starts empty; its test sources are onboarded step by step in [its demo](https://github.com/thanhphat2609/data-onboarding-ingestion/blob/main/infrastructure/non-prod/sample_database/README.md)

If something is missing, click **↻ Reload repositories**. If the platform repos changed since, note what's new: the happy path below relies on `crm_customers_current`.

The header pill shows **rule-based** or the model name. Check that it matches what you decided in 1.2.

## 1.5 Dry run (~15 min)

Run [the happy path](02_happy_path.md) parts A–D once, alone, with a throwaway requester (e.g. `dry.run@gmail.com`). Check:

- [ ] both Teams cards arrived ("New data request", then "Request approved — User Story ready")
- [ ] `outputs/<request_id>/` has `request.json`, `feasibility.json`, `user_story.md`, `us_1_spike.md`, `us_2_ingestion.md`, `us_3_transformation.md`, `user_stories_<request_id>.zip`, `summary.md`, and **no** `teams_messages.jsonl` (that file means Teams was mocked or the webhook failed)
- [ ] the session is in PostgreSQL:
  ```bash
  docker exec -it data-onboarding-postgres psql -U agent -d onboarding_agent \
    -c "SELECT request_id, requested_by, status, reviewed_by, review_action FROM sessions ORDER BY created_at DESC LIMIT 5;"
  ```
  The dry run shows `status = done`, `review_action = approve`.

Then clean up the dry run so the demo starts from an empty queue (see [postgresql.md → Clean up test sessions](../postgresql.md#clean-up-test-sessions)), and let the channel know the next cards are the demo.

## 1.6 Just before the demo

- [ ] Requester window (normal): signed in as `demo.requester@gmail.com`, on **💬 Request**, empty chat.
- [ ] Data Team window (private): signed in as `data.team@gmail.com`, on **🛡 Data Team review**.
- [ ] Teams channel visible.
- [ ] A terminal at the repo root, for showing `outputs/` and the PostgreSQL query.
- [ ] [03_results.md](03_results.md) open to fill in.

## Fallbacks

| If… | Then |
|---|---|
| The Teams webhook fails during the demo | Keep going: the card is saved to `outputs/<request_id>/teams_messages.jsonl` with `webhook_error`. Show that file |
| The model (Colab) disconnects | **⚙️ Settings → LLM → Disable LLM** and carry on rule-based |
| GitHub can't be read | The step's error appears in Settings → Repositories. Fix the token, then **↻ Reload repositories** |
| Web research (part E) is slow or empty | It stops after ~3 min per source. Say so and show the ready-made search link in the User Story; it's an optional part |
