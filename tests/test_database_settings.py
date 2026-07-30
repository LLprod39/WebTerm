from pathlib import Path

from web_ui.settings.database import build_database_settings


def test_postgres_connections_are_reused_and_health_checked(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_DB", "webterm_test")
    monkeypatch.delenv("POSTGRES_CONN_MAX_AGE_SECONDS", raising=False)

    database = build_database_settings(base_dir=tmp_path)["DATABASES"]["default"]

    assert database["CONN_MAX_AGE"] == 60
    assert database["CONN_HEALTH_CHECKS"] is True


def test_postgres_connection_max_age_is_configurable(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_CONN_MAX_AGE_SECONDS", "120")

    database = build_database_settings(base_dir=tmp_path)["DATABASES"]["default"]

    assert database["CONN_MAX_AGE"] == 120
