from web_ui.settings import security


def test_default_debug_recognizes_all_test_settings_modules(monkeypatch):
    for module in ("web_ui.settings.test", "web_ui.settings.test_postgres", "web_ui.settings.test_integration"):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
        assert security._default_debug() is True


def test_default_debug_fails_closed_for_unknown_and_production_modules(monkeypatch):
    for module in ("web_ui.settings.production", "web_ui.settings", "custom.settings"):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", module)
        assert security._default_debug() is False
