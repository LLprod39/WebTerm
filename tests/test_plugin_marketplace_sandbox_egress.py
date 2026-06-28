import copy
import json
import zipfile

import pytest
from django.test import override_settings

from app.plugins.agent_tools import active_agent_tools
from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.agent_tool_service import agent_tool_execution_provider
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.package_service import install_local_package


def _network_tool_manifest(*, plugin_id: str, slug: str, egress: list[dict] | None = None) -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": plugin_id,
        "name": "Sandbox Egress Tool",
        "slug": slug,
        "publisher": {"id": "acme", "name": "Acme"},
        "egress": egress or [],
        "surfaces": {
            "agent_tools": [
                {
                    "id": "network-probe",
                    "name": f"{slug.replace('-', '_')}_network_probe",
                    "title": "Network probe",
                    "executor_ref": "sandbox:backend/plugin.py:handle",
                    "tool_spec": {"category": "general", "risk": "network", "runner": "plugin"},
                }
            ]
        },
    })
    return manifest


def _install_network_tool(tmp_path, *, manifest: dict, code: str):
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


def _execute_tool(plugin_id: str) -> dict:
    tool = next(item for item in active_agent_tools({plugin_id}) if item["plugin_id"] == plugin_id)
    return agent_tool_execution_provider({"tool": tool, "arguments": {}})


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_backend_sandbox_blocks_undeclared_network_egress(tmp_path):
    plugin_id = "acme.blocked-egress-tool"
    _install_network_tool(
        tmp_path,
        manifest=_network_tool_manifest(plugin_id=plugin_id, slug="blocked-egress-tool"),
        code=(
            "import socket\n"
            "def handle(payload):\n"
            "    try:\n"
            "        socket.create_connection(('blocked.example', 443), timeout=0.01)\n"
            "    except Exception as exc:\n"
            "        return {'error_type': type(exc).__name__, 'message': str(exc)}\n"
            "    return {'message': 'connected'}\n"
        ),
    )

    result = _execute_tool(plugin_id)

    assert result["success"] is True
    assert result["result"]["error_type"] == "PermissionError"
    assert "Sandbox network egress to blocked.example is not declared" in result["result"]["message"]


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_backend_sandbox_allows_declared_network_egress_to_reach_os(tmp_path):
    plugin_id = "acme.allowed-egress-tool"
    _install_network_tool(
        tmp_path,
        manifest=_network_tool_manifest(
            plugin_id=plugin_id,
            slug="allowed-egress-tool",
            egress=[{"host": "127.0.0.1", "ports": [9], "reason": "Sandbox egress regression test."}],
        ),
        code=(
            "import socket\n"
            "def handle(payload):\n"
            "    try:\n"
            "        socket.create_connection(('127.0.0.1', 9), timeout=0.01)\n"
            "    except Exception as exc:\n"
            "        return {'error_type': type(exc).__name__, 'message': str(exc)}\n"
            "    return {'message': 'connected'}\n"
        ),
    )

    result = _execute_tool(plugin_id)

    assert result["success"] is True
    assert result["result"]["error_type"] != "PermissionError"
    assert "Sandbox network egress" not in result["result"]["message"]


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_EGRESS_DENIED_HOSTS=["127.0.0.1"],
)
def test_admin_denied_egress_blocks_sandbox_plugin_enable(tmp_path):
    plugin_id = "acme.denied-egress-tool"
    manifest = _network_tool_manifest(
        plugin_id=plugin_id,
        slug="denied-egress-tool",
        egress=[{"host": "127.0.0.1", "ports": [9], "reason": "Sandbox egress regression test."}],
    )
    package = tmp_path / "denied-egress-tool.wtp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", "def handle(payload):\n    return {'ok': True}\n")
    installation = install_local_package(package)
    stored = PluginPackage.objects.get(plugin_id=plugin_id)
    stored.review_status = PluginPackage.REVIEW_VERIFIED
    stored.signature_status = PluginPackage.SIGNATURE_SIGNED
    stored.save(update_fields=["review_status", "signature_status", "updated_at"])

    with pytest.raises(ValueError) as exc:
        set_installation_status(installation.id, enable=True)

    assert "Egress host denied by policy: 127.0.0.1." in str(exc.value)
