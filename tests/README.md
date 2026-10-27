# Tests

```bash
python -m pip install pytest
python -m pytest -q tests        # offline: no network, LLM or database server; CI runs the same on every push
```

| File | Covers |
|---|---|
| `conftest.py` | Every test runs offline: the repos below, outputs in a temp folder, no LLM, no web research |
| `test_extraction.py` | Intake: greeting cleanup, labelled / numbered answers, relative ETA, past ETA |
| `test_flow.py` | Whole requests through the graph: existing dbt model, new job, new connection, a source the platform can't onboard (gap), the output files and the zip |
| `test_research.py` | Web research with a fake search engine: on-topic check, history sentences, known docs, cache, learned links, engine top-up |
| `test_render_env.py` | `infrastructure/prod/render_env.py`: the prod `.env` from GitHub secrets and variables |
| `test_ui.py` | The web UI builds and a first message goes through its handler |

## Fixtures

Small copies of the two platform repos, read through `INGESTION_PATH` / `TRANSFORMATION_PATH`, with the same shapes
as the real ones:

- `ingestion/`: one source template (`sqlserver`), one onboarded system (`crm`: connection `crm-sqlserver-nonprod`,
  job `crm-customers-daily` landing `crm/dbo/customers`)
- `transformation/`: two dbt models on it (`stg_crm__customers`, `crm_customers_current`)

A new kind of case (e.g. a second source type) starts by adding its files here, not by reading the real repos.
