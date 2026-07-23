import copy
import json
import zipfile

import pytest
from django.test import override_settings

from app.plugins.agent_tools import active_agent_tools
from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation, PluginInstallEvent, PluginPackage
from plugin_marketplace.services.agent_tool_service import agent_tool_execution_provider
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.package_service import install_local_package


def _sandbox_tool_manifest(*, plugin_id: str, slug: str) -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "name": "Sandbox Health Tool",
            "slug": slug,
            "publisher": {"id": "acme", "name": "Acme"},
            "permissions": [],
            "secrets": [],
            "egress": [],
            "surfaces": {
                "agent_tools": [
                    {
                        "id": "sandbox-health",
                        "name": f"{slug.replace('-', '_')}_health",
                        "title": "Sandbox health",
                        "executor_ref": "sandbox:backend/plugin.py:handle",
                        "tool_spec": {"category": "general", "risk": "read", "runner": "plugin"},
                    }
                ]
            },
        }
    )
    return manifest


def _install_enabled_sandbox_tool(tmp_path, *, manifest: dict, code: str) -> PluginInstallation:
    package = tmp_path / f"{manifest['slug']}.wtp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", code)
    installation = install_local_package(package)
    stored = PluginPackage.objects.get(plugin_id=manifest["id"])
    stored.review_status = PluginPackage.REVIEW_VERIFIED
    stored.signature_status = PluginPackage.SIGNATURE_SIGNED
    stored.save(update_fields=["review_status", "signature_status", "updated_at"])
    return set_installation_status(installation.id, enable=True)


def _execute_agent_tool(plugin_id: str) -> dict:
    tool = next(item for item in active_agent_tools({plugin_id}) if item["plugin_id"] == plugin_id)
    return agent_tool_execution_provider({"tool": tool, "arguments": {}})


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_backend_sandbox_failures_update_health_and_auto_quarantine(tmp_path):
    plugin_id = "acme.sandbox-health-failure"
    _install_enabled_sandbox_tool(
        tmp_path,
        manifest=_sandbox_tool_manifest(plugin_id=plugin_id, slug="sandbox-health-failure"),
        code="def handle(payload):\n    raise RuntimeError('sandbox boom')\n",
    )

    for expected_count in range(1, 4):
        result = _execute_agent_tool(plugin_id)
        stored = PluginInstallation.objects.get(plugin_id=plugin_id)

        assert result["success"] is False
        assert "sandbox boom" in str(result["result"])
        assert stored.health_status == "sandbox_failed"
        assert stored.health_failure_count == expected_count
        assert "sandbox boom" in stored.last_error

    stored = PluginInstallation.objects.get(plugin_id=plugin_id)
    assert stored.status == PluginInstallation.STATUS_QUARANTINED
    assert stored.enabled_at is None
    assert stored.quarantined_at is not None
    assert (
        PluginInstallEvent.objects.filter(
            plugin_id=plugin_id,
            event_type="plugin_backend_sandbox_executed",
            status=UserActivityLog.STATUS_ERROR,
        ).count()
        == 3
    )
    assert PluginInstallEvent.objects.filter(
        plugin_id=plugin_id,
        event_type="plugin_backend_sandbox_auto_quarantined",
        status=UserActivityLog.STATUS_ERROR,
    ).exists()
