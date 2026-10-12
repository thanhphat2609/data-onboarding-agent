# playbooks/

One file per data source: `<source>.yaml` (file name = lowercase source code, e.g. `gsc.yaml`).

While this folder has **no `.yaml` files**, the agent uses the sample playbooks in `demo/playbooks/`.
As soon as it has at least one, the agent reads only this folder.

## Template

```yaml
source: gsc
display_name: Google Search Console
review_status: draft            # change to "reviewed" once the team has reviewed it
access_methods:
  - type: bigquery_bulk_export
    available_from: "YYYY-MM-DD"   # earliest date with data via this method (null if no limit)
    max_lookback_days: null        # history limit counted back from today (null if none)
    typical_lead_time_days: 5      # days the team usually needs to build the pipeline
    notes: ""
current_connector: ""
existing_models: []
owner: ""
notes: ""
```

Earliest obtainable date for an access method = `max(available_from, today - max_lookback_days)`.
Fill in retention / limits from official docs and the team's real experience — never let the agent guess.
