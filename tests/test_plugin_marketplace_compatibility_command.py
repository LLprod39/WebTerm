import copy
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource, PluginCompatibilityJob, PluginPackage


def _catalog_item(*, plugin_id: str, api_version: str = "plugins.v1") -> MarketplaceCatalogItem:
    source, _ = MarketplaceSource.objects.get_or_create(
        name="Compatibility CLI",
        defaults={"source_url": "local://compatibility-cli"},
    )
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "slug": plugin_id.rsplit(".", 1)[-1].replace("_", "-"),
            "name": plugin_id,
            "version": "1.0.0",
            "api_version": api_version,
        }
    )
    return MarketplaceCatalogItem.objects.create(
        source=source,
        plugin_id=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        compatibility={"api_versions": [api_version]},
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )


@pytest.mark.django_db
def test_compatibility_matrix_command_outputs_read_only_json():
    item = _catalog_item(plugin_id="acme.compatibility-cli-ok")
    stdout = StringIO()

    call_command("plugin_compatibility_matrix", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["summary"] == {"total": 1, "compatible": 1, "incompatible": 0}
    assert payload["items"][0]["plugin_id"] == item.plugin_id
    assert payload["items"][0]["compatible"] is True
    assert not PluginCompatibilityJob.objects.filter(catalog_item=item).exists()


@pytest.mark.django_db
def test_compatibility_matrix_command_updates_and_fails_for_incompatible_items():
    item = _catalog_item(plugin_id="acme.compatibility-cli-bad", api_version="plugins.v9")

    with pytest.raises(CommandError) as exc:
        call_command("plugin_compatibility_matrix", "--update", "--fail-on-incompatible", stdout=StringIO())

    assert "acme.compatibility-cli-bad@1.0.0" in str(exc.value)
    assert "Unsupported plugin api_version: plugins.v9" in str(exc.value)
    job = PluginCompatibilityJob.objects.get(catalog_item=item)
    assert job.status == PluginCompatibilityJob.STATUS_FAILED
    item.refresh_from_db()
    assert item.compatibility["last_matrix"]["compatible"] is False
