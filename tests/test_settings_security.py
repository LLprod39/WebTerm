from web_ui.settings import security


def test_default_debug_recognizes_all_test_settings_modules(monkeypatch):
    for module in ("web_ui.settings.test", "web_ui.settings.test_postgres", "web_ui.settings.test_integration"):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
        assert security._default_debug() is True


def test_default_debug_fails_closed_for_unknown_and_production_modules(monkeypatch):
    for module in ("web_ui.settings.production", "web_ui.settings", "custom.settings"):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
        assert security._default_debug() is False


def test_debug_defaults_contain_only_local_hosts_without_environment(monkeypatch):
    for name in (
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "SITE_URL",
        "FRONTEND_APP_URL",
        "RENDER_EXTERNAL_URL",
        "RENDER_EXTERNAL_HOSTNAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "web_ui.settings.development")
    monkeypatch.setenv("DJANGO_DEBUG", "true")

    settings = security.build_security_settings(render_external_url="", render_external_hostname="")

    assert settings["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1"]
    assert settings["CSRF_TRUSTED_ORIGINS"] == [
        "http://127.0.0.1:8080",
        "http://localhost:9000",
        "http://localhost:8080",
        "http://127.0.0.1:8081",
        "http://localhost:8081",
    ]
