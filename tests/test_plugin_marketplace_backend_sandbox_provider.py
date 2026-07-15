import base64
import copy
import io
import json
import zipfile

import pytest
from django.test import override_settings

from app.plugins.agent_tools import active_agent_tools
from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.models import (
    MarketplaceCatalogItem,
    MarketplaceSource,
    PluginCompatibilityJob,
    PluginInstallation,
    PluginPackage,
)
from plugin_marketplace.services.agent_tool_service import agent_tool_execution_provider
from plugin_marketplace.services.backend_sandbox_runner_service import execute_sandbox_package
from plugin_marketplace.services.compatibility_matrix_service import run_compatibility_job
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.package_service import install_local_package


def _sandbox_manifest(*, plugin_id: str = "acme.external-sandbox", slug: str = "external-sandbox") -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "name": "External Sandbox",
            "slug": slug,
            "version": "1.0.0",
            "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
            "permissions": [],
            "secrets": [],
            "egress": [],
            "surfaces": {
                "agent_tools": [
                    {
                        "id": "external-echo",
                        "name": f"{slug.replace('-', '_')}_echo",
                        "title": "External sandbox echo",
                        "executor_ref": "sandbox:backend/plugin.py:handle",
                        "tool_spec": {"category": "general", "risk": "read", "runner": "plugin"},
                    }
                ]
            },
            "actions": [],
        }
    )
    return manifest


def _install_enabled_package(tmp_path, manifest: dict) -> PluginInstallation:
    package_path = tmp_path / f"{manifest['slug']}.wtp"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", "def handle(payload):\n    return {'ok': True}\n")
    installation = install_local_package(package_path)
    stored = PluginPackage.objects.get(plugin_id=manifest["id"])
    stored.review_status = PluginPackage.REVIEW_VERIFIED
    stored.signature_status = PluginPackage.SIGNATURE_SIGNED
    stored.save(update_fields=["review_status", "signature_status", "updated_at"])
    return set_installation_status(installation.id, enable=True)


def _catalog_item(manifest: dict) -> MarketplaceCatalogItem:
    source = MarketplaceSource.objects.create(name="External Sandbox Catalog", source_url="local://sandbox")
    return MarketplaceCatalogItem.objects.create(
        source=source,
        plugin_id=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        compatibility={"api_versions": ["plugins.v1"]},
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="external_worker",
    PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT="https://sandbox.example/execute",
)
def test_external_backend_sandbox_provider_executes_agent_tool(tmp_path, monkeypatch):
    manifest = _sandbox_manifest()
    _install_enabled_package(tmp_path, manifest)
    requests: list[dict] = []

    def _fake_worker(url: str, payload: dict, *, timeout_seconds: int) -> dict:
        assert url == "https://sandbox.example/execute"
        assert timeout_seconds == 10
        assert zipfile.is_zipfile(io.BytesIO(base64.b64decode(payload["package_b64"])))
        assert payload["executor_ref"] == "sandbox:backend/plugin.py:handle"
        assert payload["smoke_only"] is False
        assert payload["payload"]["plugin_id"] == manifest["id"]
        requests.append(payload)
        return {"success": True, "result": {"provider": "external_worker", "surface": payload["payload"]["payload"]["surface"]}}

    monkeypatch.setattr("plugin_marketplace.services.backend_sandbox_runner_service._post_json", _fake_worker)

    tool = next(item for item in active_agent_tools({manifest["id"]}) if item["plugin_id"] == manifest["id"])
    result = agent_tool_execution_provider({"tool": tool, "arguments": {"message": "hello"}})

    assert result["success"] is True
    assert result["result"] == {"provider": "external_worker", "surface": "agent_tool"}
    assert len(requests) == 1


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="external_worker",
    PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT="https://sandbox.example/execute",
)
def test_external_backend_sandbox_provider_runs_compatibility_smoke(tmp_path, monkeypatch):
    manifest = _sandbox_manifest(plugin_id="acme.external-compat", slug="external-compat")
    package_path = tmp_path / "external-compat.wtp"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", "def handle(payload):\n    return {'ok': True}\n")
    install_local_package(package_path)
    item = _catalog_item(manifest)

    def _fake_worker(url: str, payload: dict, *, timeout_seconds: int) -> dict:
        assert url == "https://sandbox.example/execute"
        assert payload["smoke_only"] is True
        assert payload["payload"]["surface"] == "compatibility_job"
        return {"success": True, "result": {"loaded": True, "executor_ref": payload["executor_ref"]}}

    monkeypatch.setattr("plugin_marketplace.services.backend_sandbox_runner_service._post_json", _fake_worker)

    job = run_compatibility_job(item, isolation_mode="subprocess_sandbox")

    assert job.status == PluginCompatibilityJob.STATUS_PASSED
    smoke = next(check for check in job.checks if check["name"] == "sandbox_executor_smoke")
    assert smoke["ok"] is True
    assert smoke["results"][0]["result"]["result"]["loaded"] is True


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="unknown",
)
def test_deploy_check_rejects_unknown_backend_sandbox_provider():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E021"}


@override_settings(PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="unknown")
def test_unknown_backend_sandbox_provider_returns_runtime_error():
    result = execute_sandbox_package(
        package_bytes=b"unused",
        executor_ref="sandbox:backend/plugin.py:handle",
        payload={},
    )

    assert result["success"] is False
    assert result["error"] == "Backend sandbox provider is unknown: unknown."


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="external_worker",
    PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT="http://sandbox.example/execute",
)
def test_deploy_check_requires_https_external_backend_sandbox_endpoint():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E022"}


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="local_subprocess",
)
def test_deploy_check_requires_external_backend_sandbox_provider_for_production_code_packages():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E023"}
