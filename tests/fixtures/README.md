# Test fixtures

Small copies of the two platform repos, read through `INGESTION_PATH` / `TRANSFORMATION_PATH` so the tests need no
network. Same shapes as the real repos: one source template (`sqlserver`), one onboarded system (`crm`, connection
`crm-sqlserver-nonprod`, job `crm-customers-daily` landing `crm/dbo/customers`) and two dbt models on it.
