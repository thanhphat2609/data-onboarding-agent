"""infrastructure/prod/render_env.py: the prod .env written by the Deploy workflow from GitHub secrets and variables."""
import importlib.util
import json
import stat

from conftest import ROOT

spec = importlib.util.spec_from_file_location("render_env", ROOT / "infrastructure/prod/render_env.py")
render_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_env)

EXAMPLE = ROOT / "infrastructure/prod/.env.example"
SECRETS = {"POSTGRES_PASSWORD": "a", "POSTGRES_AGENT_PASSWORD": "b", "POSTGRES_AIRFLOW_PASSWORD": "c",
           "POSTGRES_PLATFORM_PASSWORD": "d", "PLATFORM_GITHUB_TOKEN": "t", "ACCOUNTS": "team@x.com:p$w",
           "SEARXNG_SECRET": "s", "TEAMS_WEBHOOK_URL": "https://x/flows?api-version=1&sp=%2Ftriggers", "github_token": "x"}


def run(tmp_path, monkeypatch, secrets, variables):
    monkeypatch.setenv("SECRETS_JSON", json.dumps(secrets))
    monkeypatch.setenv("VARS_JSON", json.dumps(variables))
    out = tmp_path / "prod.env"
    return render_env.main([str(EXAMPLE), str(out)]), out


def test_writes_every_key_quoted_and_private(tmp_path, monkeypatch):
    code, out = run(tmp_path, monkeypatch, SECRETS, {"DATA_TEAM": "team@x.com"})
    assert code == 0
    text = out.read_text()
    assert "ACCOUNTS='team@x.com:p$w'" in text
    assert "TEAMS_WEBHOOK_URL='https://x/flows?api-version=1&sp=%2Ftriggers'" in text
    assert "OLLAMA_HOST=''" in text  # unset: the compose default applies
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_missing_secret_stops(tmp_path, monkeypatch, capsys):
    secrets = {k: v for k, v in SECRETS.items() if k != "SEARXNG_SECRET"}
    code, out = run(tmp_path, monkeypatch, secrets, {})
    assert code == 1 and not out.exists()
    assert "SEARXNG_SECRET is missing" in capsys.readouterr().out


def test_password_saved_as_a_variable_stops(tmp_path, monkeypatch, capsys):
    secrets = {k: v for k, v in SECRETS.items() if k != "ACCOUNTS"}
    code, _ = run(tmp_path, monkeypatch, secrets, {"ACCOUNTS": "team@x.com:p"})
    assert code == 1
    assert "ACCOUNTS is a repository variable" in capsys.readouterr().out


def test_quote_in_a_value_stops(tmp_path, monkeypatch, capsys):
    code, _ = run(tmp_path, monkeypatch, {**SECRETS, "SEARXNG_SECRET": "it's"}, {})
    assert code == 1
    assert "single quote" in capsys.readouterr().out


def test_todo_placeholders_stop_even_for_settings_not_in_the_file(tmp_path, monkeypatch, capsys):
    code, _ = run(tmp_path, monkeypatch, SECRETS, {"PROD_REPO_DIR": "todo", "OLLAMA_HOST": "TODO"})
    assert code == 1
    printed = capsys.readouterr().out
    assert "PROD_REPO_DIR is still TODO" in printed and "OLLAMA_HOST is still TODO" in printed
