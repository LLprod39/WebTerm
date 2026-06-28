from web_ui.settings.plugin_marketplace import build_plugin_marketplace_settings


def test_plugin_marketplace_settings_reads_catalog_source_allowlist(monkeypatch):
    monkeypatch.setenv("PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS", "catalog.example, feeds.example")

    settings = build_plugin_marketplace_settings(debug=False)

    assert settings["PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS"] == [
        "catalog.example",
        "feeds.example",
    ]
