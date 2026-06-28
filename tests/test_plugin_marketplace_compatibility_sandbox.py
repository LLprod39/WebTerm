import copy
import json
import zipfile

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.models import MarketplaceCatalogItem, MarketplaceSource, PluginCompatibilityJob
from plugin_marketplace.services.compatibility_matrix_service import run_compatibility_job
from plugin_marketplace.services.package_service import install_local_package


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


def _sandbox_manifest(*, plugin_id: str = "acme.compat-sandbox", slug: str = "compat-sandbox") -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "name": "Compatibility Sandbox",
            "slug": slug,
            "version": "1.0.0",
            "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
            "permissions": [],
            "secrets": [],
            "egress": [],
            "surfaces": {
                "agent_tools": [
                    {
                        "id": "compat-smoke",
                        "name": f"{slug.replace('-', '_')}_compat_smoke",
                        "title": "Compatibility smoke",
                        "executor_ref": "sandbox:backend/plugin.py:handle",
                        "tool_spec": {"category": "general", "risk": "read", "runner": "plugin"},
                    }
                ]
            },
            "actions": [],
        }
    )
    return manifest


def _write_package(tmp_path, manifest: dict, code: str = "def handle(payload):\n    return {'ok': True}\n") -> str:
    package = tmp_path / f"{manifest['slug']}.wtp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", code)
    return str(package)


def _catalog_item(manifest: dict) -> MarketplaceCatalogItem:
    source = MarketplaceSource.objects.create(name="Sandbox Compatibility", source_url="local://compatibility")
    return MarketplaceCatalogItem.objects.create(
        source=source,
        plugin_id=manifest["id"],
        version=manifest["version"],
        manifest=manifest,
        compatibility={"api_versions": ["plugins.v1"]},
        review_status="verified",
        signature_status="signed",
    )


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_subprocess_sandbox_compatibility_job_loads_retained_executor(tmp_path):
    manifest = _sandbox_manifest()
    install_local_package(_write_package(tmp_path, manifest))
    item = _catalog_item(manifest)

    job = run_compatibility_job(item, isolation_mode="subprocess_sandbox")

    assert job.status == PluginCompatibilityJob.STATUS_PASSED
    assert job.isolation_mode == "subprocess_sandbox"
    smoke = next(check for check in job.checks if check["name"] == "sandbox_executor_smoke")
    assert smoke["ok"] is True
    assert smoke["executor_refs"] == ["sandbox:backend/plugin.py:handle"]
    assert smoke["results"][0]["result"]["success"] is True
    assert smoke["results"][0]["result"]["result"]["loaded"] is True


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_subprocess_sandbox_compatibility_job_runs_manifest_test_cases(tmp_path):
    manifest = _sandbox_manifest(plugin_id="acme.compat-case", slug="compat-case")
    manifest["compatibility_tests"] = [
        {
            "id": "echo-value",
            "executor_ref": "sandbox:backend/plugin.py:handle",
            "payload": {"surface": "compatibility_job", "arguments": {"value": "expected"}},
            "expect": {"result.echo": "expected"},
        }
    ]
    install_local_package(
        _write_package(
            tmp_path,
            manifest,
            "def handle(payload):\n    return {'echo': payload.get('arguments', {}).get('value')}\n",
        )
    )
    item = _catalog_item(manifest)

    job = run_compatibility_job(item, isolation_mode="subprocess_sandbox")

    assert job.status == PluginCompatibilityJob.STATUS_PASSED
    tests = next(check for check in job.checks if check["name"] == "sandbox_compatibility_tests")
    assert tests["ok"] is True
    assert tests["cases"][0]["id"] == "echo-value"
    assert tests["cases"][0]["expectations"][0]["actual"] == "expected"


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_subprocess_sandbox_compatibility_job_fails_without_retained_package():
    item = _catalog_item(_sandbox_manifest(plugin_id="acme.compat-missing", slug="compat-missing"))

    job = run_compatibility_job(item, isolation_mode="subprocess_sandbox")

    assert job.status == PluginCompatibilityJob.STATUS_FAILED
    smoke = next(check for check in job.checks if check["name"] == "sandbox_executor_smoke")
    assert smoke["ok"] is False
    assert smoke["error"] == "Retained plugin package was not found."


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_compatibility_jobs_api_accepts_subprocess_sandbox_mode(tmp_path):
    user = User.objects.create_user(username="compat-sandbox-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    manifest = _sandbox_manifest(plugin_id="acme.compat-api", slug="compat-api")
    install_local_package(_write_package(tmp_path, manifest))
    item = _catalog_item(manifest)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/plugins/marketplace/compatibility-jobs/",
        data=_json({"catalog_item_id": item.id, "isolation_mode": "subprocess_sandbox"}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["job"]["status"] == PluginCompatibilityJob.STATUS_PASSED
    assert response.json()["job"]["isolation_mode"] == "subprocess_sandbox"


@pytest.mark.django_db
def test_compatibility_jobs_api_rejects_unknown_isolation_mode():
    user = User.objects.create_user(username="compat-mode-admin", password="x", is_staff=True)
    _grant_feature(user, "settings")
    item = _catalog_item(_sandbox_manifest(plugin_id="acme.compat-mode", slug="compat-mode"))
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/plugins/marketplace/compatibility-jobs/",
        data=_json({"catalog_item_id": item.id, "isolation_mode": "subprocess_typo"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_compatibility_job"
    assert "Unsupported compatibility isolation mode" in response.json()["error"]
    assert not PluginCompatibilityJob.objects.filter(catalog_item=item).exists()


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE="subprocess_sandbox",
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=False,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=False,
)
def test_deploy_check_blocks_sandbox_compatibility_mode_without_backend_sandbox():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E019"}


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE="unknown",
)
def test_deploy_check_rejects_unknown_compatibility_isolation_mode():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E018"}
