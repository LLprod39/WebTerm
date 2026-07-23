import json

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.models import PluginInstallation, PluginInstallEvent, PluginPackage, PluginSecretBinding
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.signing_service import canonical_manifest_hash


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


@pytest.mark.django_db
def test_pending_unsigned_package_cannot_enable_until_reviewed_and_signed():
    user = User.objects.create_user(username="plugin-reviewer", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.reviewed",
            "name": "Reviewed Plugin",
            "slug": "reviewed",
            "publisher": {"id": "acme", "name": "Acme"},
        }
    )
    package = PluginPackage.objects.create(
        plugin_id="acme.reviewed",
        version="0.1.0",
        name="Reviewed Plugin",
        slug="reviewed",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_LOCAL,
        manifest=manifest,
        review_status=PluginPackage.REVIEW_PENDING,
        signature_status=PluginPackage.SIGNATURE_UNSIGNED,
    )
    installation = PluginInstallation.objects.create(plugin_id="acme.reviewed", package=package)

    blocked = client.post(f"/api/plugins/installed/{installation.id}/enable/")
    assert blocked.status_code == 409
    assert "review status is pending" in blocked.json()["error"]

    queue = client.get("/api/plugins/review/packages/")
    assert queue.status_code == 200
    assert any(item["id"] == package.id for item in queue.json()["packages"])

    reviewed = client.post(
        f"/api/plugins/review/packages/{package.id}/review/",
        data=_json({"status": "verified", "notes": "Internal review passed."}),
        content_type="application/json",
    )
    assert reviewed.status_code == 200, reviewed.content
    package.refresh_from_db()
    assert package.review_status == PluginPackage.REVIEW_VERIFIED
    assert package.signature_status == PluginPackage.SIGNATURE_SIGNED
    assert package.package_hash == canonical_manifest_hash(manifest)
    assert package.signature_payload["alg"] == "hmac-sha256"
    assert package.signature_payload["key_id"]

    package.provenance = {"tampered": True}
    package.save(update_fields=["provenance", "updated_at"])
    verified_signature = client.post(f"/api/plugins/review/packages/{package.id}/verify-signature/")
    assert verified_signature.status_code == 200, verified_signature.content
    package.refresh_from_db()
    assert package.signature_status == PluginPackage.SIGNATURE_INVALID

    blocked_invalid = client.post(f"/api/plugins/installed/{installation.id}/enable/")
    assert blocked_invalid.status_code == 409
    assert "signature status is invalid" in blocked_invalid.json()["error"]

    resigned = client.post(f"/api/plugins/review/packages/{package.id}/sign/")
    assert resigned.status_code == 200, resigned.content
    package.refresh_from_db()
    assert package.signature_status == PluginPackage.SIGNATURE_SIGNED

    enabled = client.post(f"/api/plugins/installed/{installation.id}/enable/")
    assert enabled.status_code == 200, enabled.content
    assert enabled.json()["status"] == PluginInstallation.STATUS_ENABLED
    assert PluginInstallEvent.objects.filter(plugin_id="acme.reviewed", event_type="plugin_package_signed").exists()
    assert PluginInstallEvent.objects.filter(plugin_id="acme.reviewed", event_type="plugin_package_reviewed").exists()


@pytest.mark.django_db
def test_lifecycle_impact_update_soft_uninstall_and_rollback():
    user = User.objects.create_user(username="plugin-lifecycle", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)

    base_manifest = dict(DEMO_PLUGIN_MANIFEST)
    base_manifest.update(
        {
            "id": "acme.lifecycle",
            "name": "Lifecycle Plugin",
            "slug": "lifecycle",
            "publisher": {"id": "acme", "name": "Acme"},
            "version": "0.1.0",
            "settings_schema": {
                "type": "object",
                "properties": {"display_label": {"type": "string"}},
            },
            "secrets": [{"id": "api_token", "label": "API token", "kind": "bearer_token", "required": True}],
        }
    )
    next_manifest = dict(base_manifest)
    next_manifest.update(
        {
            "version": "0.2.0",
            "permissions": [
                *base_manifest["permissions"],
                {"scope": "acme.lifecycle.write", "reason": "Write lifecycle output.", "risk_tier": "internal_write"},
            ],
            "settings_schema": {
                "type": "object",
                "properties": {
                    "display_label": {"type": "string"},
                    "channel": {"type": "string"},
                },
            },
            "secrets": [
                *base_manifest["secrets"],
                {"id": "webhook_token", "label": "Webhook token", "kind": "bearer_token", "required": True},
            ],
            "egress": [{"hosts": ["hooks.example.com"]}],
        }
    )
    package_v1 = PluginPackage.objects.create(
        plugin_id="acme.lifecycle",
        version="0.1.0",
        name="Lifecycle Plugin",
        slug="lifecycle",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_LOCAL,
        package_hash=canonical_manifest_hash(base_manifest),
        manifest=base_manifest,
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )
    package_v2 = PluginPackage.objects.create(
        plugin_id="acme.lifecycle",
        version="0.2.0",
        name="Lifecycle Plugin",
        slug="lifecycle",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_LOCAL,
        package_hash=canonical_manifest_hash(next_manifest),
        manifest=next_manifest,
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )
    installation = PluginInstallation.objects.create(
        plugin_id="acme.lifecycle",
        package=package_v1,
        status=PluginInstallation.STATUS_ENABLED,
        settings={"display_label": "Ops"},
    )
    PluginSecretBinding.objects.create(installation=installation, key="api_token", secret_ref="managed-api-token")

    impact = client.get(f"/api/plugins/installed/{installation.id}/impact/")
    assert impact.status_code == 200, impact.content
    assert impact.json()["impact"]["secrets"]["missing_required"] == []
    assert impact.json()["impact"]["package"]["ready_to_enable"] is True

    preview = client.post(
        f"/api/plugins/installed/{installation.id}/update-preview/",
        data=_json({"package_id": package_v2.id}),
        content_type="application/json",
    )
    assert preview.status_code == 200, preview.content
    report = preview.json()["impact"]
    assert report["permissions"]["added"] == ["acme.lifecycle.write"]
    assert report["secrets"]["added"] == ["webhook_token"]
    assert report["egress_hosts"]["added"] == ["hooks.example.com"]
    assert report["requires_permission_review"] is True

    updated = client.post(
        f"/api/plugins/installed/{installation.id}/update-package/",
        data=_json({"package_id": package_v2.id}),
        content_type="application/json",
    )
    assert updated.status_code == 200, updated.content
    installation.refresh_from_db()
    assert installation.package_id == package_v2.id
    assert installation.status == PluginInstallation.STATUS_DISABLED

    rollback = client.post(
        f"/api/plugins/installed/{installation.id}/rollback/",
        data=_json({}),
        content_type="application/json",
    )
    assert rollback.status_code == 200, rollback.content
    installation.refresh_from_db()
    assert installation.package_id == package_v1.id
    assert installation.status == PluginInstallation.STATUS_DISABLED

    uninstalled = client.post(
        f"/api/plugins/installed/{installation.id}/soft-uninstall/",
        data=_json({}),
        content_type="application/json",
    )
    assert uninstalled.status_code == 200, uninstalled.content
    installation.refresh_from_db()
    assert installation.status == PluginInstallation.STATUS_DISABLED
    assert installation.settings == {"display_label": "Ops"}
    assert PluginSecretBinding.objects.filter(installation=installation, key="api_token").exists()
    assert PluginInstallEvent.objects.filter(plugin_id="acme.lifecycle", event_type="plugin_soft_uninstalled").exists()


@pytest.mark.django_db
def test_sandbox_policy_blocks_dynamic_plugin_enable_until_sandbox_is_enabled():
    user = User.objects.create_user(username="plugin-sandbox", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.sandboxed",
            "name": "Sandboxed Plugin",
            "slug": "sandboxed",
            "publisher": {"id": "acme", "name": "Acme"},
            "surfaces": {
                "pages": [{"id": "dynamic", "title": "Dynamic", "renderer": "iframe_sandbox"}],
                "agent_tools": [{"name": "acme_dynamic", "executor_ref": "acme.worker.run"}],
            },
        }
    )
    package = PluginPackage.objects.create(
        plugin_id="acme.sandboxed",
        version="0.1.0",
        name="Sandboxed Plugin",
        slug="sandboxed",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_LOCAL,
        package_hash=canonical_manifest_hash(manifest),
        manifest=manifest,
        sbom={
            "files": [
                {"path": "backend/plugin.py", "size": 120, "sha256": "abc", "safe_path": True},
                {"path": "frontend/components/index.js", "size": 220, "sha256": "def", "safe_path": True},
            ]
        },
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )
    installation = PluginInstallation.objects.create(plugin_id="acme.sandboxed", package=package)

    impact = client.get(f"/api/plugins/installed/{installation.id}/impact/")
    assert impact.status_code == 200, impact.content
    sandbox_policy = impact.json()["impact"]["package"]["sandbox_policy"]
    assert sandbox_policy["required"] is True
    assert sandbox_policy["allowed"] is False
    assert "Backend sandbox runtime is not enabled." in sandbox_policy["blockers"]

    blocked = client.post(f"/api/plugins/installed/{installation.id}/enable/")
    assert blocked.status_code == 409
    assert "Sandbox policy" in blocked.json()["error"]

    with override_settings(
        PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
        PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
        PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    ):
        ready = client.get(f"/api/plugins/installed/{installation.id}/impact/")
        assert ready.status_code == 200, ready.content
        assert ready.json()["impact"]["package"]["sandbox_policy"]["allowed"] is True
        assert ready.json()["impact"]["package"]["ready_to_enable"] is True


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_sandbox_policy_blocks_stored_dependency_scan_blockers():
    manifest = dict(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.blocked-dependency",
            "name": "Blocked Dependency",
            "slug": "blocked-dependency",
            "publisher": {"id": "acme", "name": "Acme"},
        }
    )
    package = PluginPackage.objects.create(
        plugin_id="acme.blocked-dependency",
        version="0.1.0",
        name="Blocked Dependency",
        slug="blocked-dependency",
        publisher_id="acme",
        publisher_name="Acme",
        source=PluginPackage.SOURCE_LOCAL,
        manifest=manifest,
        sbom={
            "files": [{"path": "requirements.txt", "size": 16, "sha256": "abc", "safe_path": True}],
            "components": [{"ecosystem": "python", "name": "requests", "source": "requirements.txt"}],
            "dependency_manifests": [{"path": "requirements.txt", "parse_supported": True}],
        },
        dependency_scan={
            "passed": False,
            "blockers": [{"code": "dependency_not_allowlisted", "dependency": "python:requests"}],
        },
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )
    installation = PluginInstallation.objects.create(plugin_id="acme.blocked-dependency", package=package)

    with pytest.raises(ValueError) as exc:
        set_installation_status(installation.id, enable=True)

    assert "Dependency policy dependency_not_allowlisted: python:requests" in str(exc.value)
