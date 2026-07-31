from web_ui.settings.plugin_marketplace import build_plugin_marketplace_settings


def test_plugin_backend_execution_defaults_local_in_debug_and_disabled_in_production(monkeypatch):
    monkeypatch.delenv("PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER", raising=False)

    assert (
        build_plugin_marketplace_settings(debug=True)["PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER"]
        == "local_subprocess"
    )
    assert build_plugin_marketplace_settings(debug=False)["PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER"] == "disabled"


def test_plugin_marketplace_settings_reads_catalog_source_allowlist(monkeypatch):
    monkeypatch.setenv("PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS", "catalog.example, feeds.example")

    settings = build_plugin_marketplace_settings(debug=False)

    assert settings["PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS"] == [
        "catalog.example",
        "feeds.example",
    ]
