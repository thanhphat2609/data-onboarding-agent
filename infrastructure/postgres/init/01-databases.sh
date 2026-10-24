#!/bin/sh
# Runs once, when the postgres volume is empty (docker-entrypoint-initdb.d). One server, one database per owner:
#   onboarding_agent  owner agent     this app: LangGraph checkpoints + sessions (tables created by the app)
#   airflow           owner airflow   Airflow metadata DB (tables created by `airflow db migrate`)
#   platform          owner platform  data-onboarding-ingestion run records (runs, run_events; its architecture §3.4)
# Changing a password later: ALTER ROLE ... PASSWORD, or recreate the volume (docker compose down -v deletes ALL data).
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v agent_pw="$AGENT_DB_PASSWORD" -v airflow_pw="$AIRFLOW_DB_PASSWORD" -v platform_pw="$PLATFORM_DB_PASSWORD" <<'SQL'
CREATE ROLE agent LOGIN PASSWORD :'agent_pw';
CREATE DATABASE onboarding_agent OWNER agent;
REVOKE ALL ON DATABASE onboarding_agent FROM PUBLIC;

CREATE ROLE airflow LOGIN PASSWORD :'airflow_pw';
CREATE DATABASE airflow OWNER airflow;
REVOKE ALL ON DATABASE airflow FROM PUBLIC;

CREATE ROLE platform LOGIN PASSWORD :'platform_pw';
CREATE DATABASE platform OWNER platform;
REVOKE ALL ON DATABASE platform FROM PUBLIC;
SQL
