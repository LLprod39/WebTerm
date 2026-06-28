import copy

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.test import override_settings

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from core_ui.models import UserAppPermission
from plugin_marketplace.checks import plugin_marketplace_deploy_check
from plugin_marketplace.models import PluginInstallation, PluginPackage
from plugin_marketplace.services.frontend_bundle_policy_service import FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.lifecycle_service import installation_impact
from plugin_marketplace.services.package_attestation_service import append_package_attestation
from plugin_marketplace.services.signing_service import canonical_manifest_hash
from plugin_marketplace.services.static_scan_service import scan_manifest


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _manifest(*, plugin_id: str = "acme.dynamic-frontend", slug: str = "dynamic-frontend") -> dict:
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": plugin_id,
            "name": "Dynamic Frontend",
            "slug": slug,
            "version": "1.0.0",
            "publisher": {"id": "acme", "name": "Acme Apps", "verified": True},
            "permissions": [],
            "secrets": [],
            "egress": [],
            "surfaces": {
                "pages": [
                    {
                        "id": "dynamic",
                        "title": "Dynamic",
                        "renderer": "javascript",
                        "bundle_url": "https://cdn.example/plugins/dynamic.js",
                        "bundle_sha256": "a" * 64,
                    }
                ]
            },
            "actions": [],
        }
    )
    return manifest


def _package(manifest: dict) -> PluginPackage:
    return PluginPackage.objects.create(
        plugin_id=manifest["id"],
        version=manifest["version"],
        name=manifest["name"],
        slug=manifest["slug"],
        publisher_id="acme",
        publisher_name="Acme Apps",
        source=PluginPackage.SOURCE_CATALOG,
        package_hash=canonical_manifest_hash(manifest),
        manifest=manifest,
        review_status=PluginPackage.REVIEW_VERIFIED,
        signature_status=PluginPackage.SIGNATURE_SIGNED,
    )


def test_static_scan_blocks_dynamic_frontend_bundles_without_explicit_policy_flag():
    manifest = _manifest()

    blocked = scan_manifest(manifest, allow_sandboxed_code=True)

    assert blocked.passed is False
    assert [finding.code for finding in blocked.findings] == ["dynamic_frontend_renderer"]

    misconfigured = scan_manifest(manifest, allow_dynamic_frontend_bundles=True)
    assert misconfigured.passed is False
    assert [finding.code for finding in misconfigured.findings] == ["dynamic_frontend_renderer"]

    allowed = scan_manifest(
        manifest,
        allow_sandboxed_code=True,
        allow_dynamic_frontend_bundles=True,
    )
    assert allowed.passed is True

    missing_integrity = copy.deepcopy(manifest)
    missing_integrity["surfaces"]["pages"][0].pop("bundle_sha256")
    invalid = scan_manifest(
        missing_integrity,
        allow_sandboxed_code=True,
        allow_dynamic_frontend_bundles=True,
    )
    assert invalid.passed is False
    assert [finding.code for finding in invalid.findings] == ["dynamic_frontend_bundle_integrity"]


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
)
def test_dynamic_frontend_bundle_enable_requires_matching_review_attestation():
    manifest = _manifest(plugin_id="acme.dynamic-frontend-reviewed", slug="dynamic-frontend-reviewed")
    package = _package(manifest)
    installation = PluginInstallation.objects.create(plugin_id=package.plugin_id, package=package)

    impact = installation_impact(installation)
    frontend_policy = impact["package"]["sandbox_policy"]["frontend_bundle_policy"]
    assert frontend_policy["required"] is True
    assert frontend_policy["allowed"] is False
    assert f"Required attestation missing or stale: {FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND}." in frontend_policy["blockers"]

    with pytest.raises(ValueError) as missing_attestation:
        set_installation_status(installation.id, enable=True)
    assert "Frontend bundle policy" in str(missing_attestation.value)

    append_package_attestation(
        package,
        kind=FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        status="passed",
        report={"package_hash": "stale-package-hash"},
    )
    blocked = installation_impact(installation)
    assert blocked["package"]["sandbox_policy"]["frontend_bundle_policy"]["allowed"] is False

    append_package_attestation(
        package,
        kind=FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        status="passed",
        report={
            "package_hash": package.package_hash,
            "manifest_hash": canonical_manifest_hash(manifest),
        },
    )
    package.refresh_from_db()

    ready = installation_impact(installation)
    assert ready["package"]["sandbox_policy"]["frontend_bundle_policy"]["allowed"] is True
    assert ready["package"]["ready_to_enable"] is True

    enabled = set_installation_status(installation.id, enable=True)
    assert enabled.status == PluginInstallation.STATUS_ENABLED


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
)
def test_dynamic_frontend_bundle_policy_requires_https_url_and_integrity():
    manifest = _manifest(plugin_id="acme.dynamic-frontend-invalid", slug="dynamic-frontend-invalid")
    manifest["surfaces"]["pages"][0]["bundle_url"] = "http://cdn.example/plugins/dynamic.js"
    manifest["surfaces"]["pages"][0]["bundle_sha256"] = "not-a-sha"
    package = _package(manifest)
    installation = PluginInstallation.objects.create(plugin_id=package.plugin_id, package=package)
    append_package_attestation(
        package,
        kind=FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        status="passed",
        report={
            "package_hash": package.package_hash,
            "manifest_hash": canonical_manifest_hash(manifest),
        },
    )
    package.refresh_from_db()

    impact = installation_impact(installation)
    frontend_policy = impact["package"]["sandbox_policy"]["frontend_bundle_policy"]

    assert frontend_policy["allowed"] is False
    assert "surfaces.pages[0]: Dynamic frontend bundle URL must be HTTPS." in frontend_policy["blockers"]
    assert "surfaces.pages[0]: Dynamic frontend bundle must declare a 64-character SHA-256 hex digest." in frontend_policy["blockers"]

    with pytest.raises(ValueError) as exc:
        set_installation_status(installation.id, enable=True)
    assert "Dynamic frontend bundle URL must be HTTPS" in str(exc.value)


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
    PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS=["trusted-cdn.example"],
)
def test_dynamic_frontend_bundle_policy_blocks_untrusted_bundle_hosts():
    manifest = _manifest(plugin_id="acme.dynamic-frontend-host", slug="dynamic-frontend-host")
    package = _package(manifest)
    installation = PluginInstallation.objects.create(plugin_id=package.plugin_id, package=package)
    append_package_attestation(
        package,
        kind=FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        status="passed",
        report={
            "package_hash": package.package_hash,
            "manifest_hash": canonical_manifest_hash(manifest),
        },
    )

    impact = installation_impact(installation)
    frontend_policy = impact["package"]["sandbox_policy"]["frontend_bundle_policy"]

    assert frontend_policy["allowed"] is False
    assert "surfaces.pages[0]: Dynamic frontend bundle host is not allowed." in frontend_policy["blockers"]


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
)
def test_enabled_dynamic_frontend_page_exposes_runtime_metadata_only_after_policy_passes():
    user = User.objects.create_user(username="dynamic-frontend-page", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    manifest = _manifest(plugin_id="acme.dynamic-frontend-page", slug="dynamic-frontend-page")
    package = _package(manifest)
    installation = PluginInstallation.objects.create(plugin_id=package.plugin_id, package=package)

    disabled_page = client.get(f"/api/plugins/pages/{package.plugin_id}/dynamic/")
    assert disabled_page.status_code == 404

    append_package_attestation(
        package,
        kind=FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        status="passed",
        report={
            "package_hash": package.package_hash,
            "manifest_hash": canonical_manifest_hash(manifest),
        },
    )
    package.refresh_from_db()
    set_installation_status(installation.id, enable=True)

    page = client.get(f"/api/plugins/pages/{package.plugin_id}/dynamic/")

    assert page.status_code == 200, page.content
    runtime = page.json()["page"]["frontend_bundle_runtime"]
    assert runtime["renderer"] == "javascript"
    assert runtime["bundle_url"] == "https://cdn.example/plugins/dynamic.js"
    assert runtime["bundle_sha256"] == "a" * 64
    assert runtime["sandbox"] == {"allow_scripts": True}
    assert runtime["required_attestation_kind"] == FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
)
def test_enabled_dynamic_dashboard_widget_exposes_runtime_metadata_only_after_policy_passes():
    user = User.objects.create_user(username="dynamic-widget-user", password="x", is_staff=True)
    _grant_feature(user, "settings")
    client = Client()
    client.force_login(user)
    manifest = _manifest(plugin_id="acme.dynamic-widget", slug="dynamic-widget")
    manifest["surfaces"] = {
        "dashboard_widgets": [
            {
                "id": "dynamic-widget",
                "title": "Dynamic Widget",
                "renderer": "remote",
                "bundle_url": "https://cdn.example/plugins/widget.js",
                "bundle_sha256": "b" * 64,
            }
        ]
    }
    package = _package(manifest)
    installation = PluginInstallation.objects.create(plugin_id=package.plugin_id, package=package)

    before = client.get("/api/plugins/surfaces/")
    assert before.status_code == 200
    assert before.json()["surfaces"]["dashboard_widgets"] == []

    append_package_attestation(
        package,
        kind=FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND,
        status="passed",
        report={
            "package_hash": package.package_hash,
            "manifest_hash": canonical_manifest_hash(manifest),
        },
    )
    package.refresh_from_db()
    set_installation_status(installation.id, enable=True)

    active = client.get("/api/plugins/surfaces/")

    assert active.status_code == 200, active.content
    widget = active.json()["surfaces"]["dashboard_widgets"][0]
    runtime = widget["frontend_bundle_runtime"]
    assert widget["id"] == "dynamic-widget"
    assert runtime["renderer"] == "remote"
    assert runtime["bundle_url"] == "https://cdn.example/plugins/widget.js"
    assert runtime["bundle_sha256"] == "b" * 64
    assert runtime["required_attestation_kind"] == FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND


@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=False,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=False,
)
def test_deploy_check_requires_frontend_sandbox_before_dynamic_bundles_are_allowed():
    assert "plugin_marketplace.E024" in {error.id for error in plugin_marketplace_deploy_check(None)}


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER=False,
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="external_worker",
    PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT="https://sandbox.example/execute",
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
    PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=[],
    PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER="external_artifact_host",
    PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_ENDPOINT="https://bundles.example/readiness",
    PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS=["cdn.example"],
)
def test_deploy_check_requires_frontend_bundle_review_attestation_in_production():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {"plugin_marketplace.E025"}


@override_settings(
    DEBUG=False,
    PLUGIN_MARKETPLACE_SIGNING_KEYS={"prod-1": "secret"},
    PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID="prod-1",
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER=False,
    PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER=False,
    PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS=["packages.example"],
    PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS=["catalog.example"],
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER="external_worker",
    PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT="https://sandbox.example/execute",
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES=True,
    PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS=[FRONTEND_BUNDLE_REVIEW_ATTESTATION_KIND],
)
def test_deploy_check_requires_external_frontend_bundle_artifact_host_in_production():
    assert {error.id for error in plugin_marketplace_deploy_check(None)} == {
        "plugin_marketplace.E027",
        "plugin_marketplace.E029",
    }
