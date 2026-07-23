import copy
import json
import zipfile
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from app.plugins.agent_tools import active_agent_tools
from app.plugins.catalog import DEMO_PLUGIN_MANIFEST, project_plugin_catalog
from app.plugins.surfaces import active_plugin_surfaces
from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from plugin_marketplace.models import PluginInstallation, PluginPackage
from plugin_marketplace.services.agent_tool_service import agent_tool_execution_provider
from plugin_marketplace.services.developer_package_service import validate_plugin_source_dir
from plugin_marketplace.services.install_service import set_installation_status
from plugin_marketplace.services.package_retention_service import retained_package_exists
from plugin_marketplace.services.package_service import install_local_package, validate_wtp_package


def test_plugin_catalog_hides_surfaces_until_enabled():
    disabled = project_plugin_catalog(set())
    enabled = project_plugin_catalog({"webtrerm.demo-dashboard"})

    demo_disabled = next(item for item in disabled if item["id"] == "webtrerm.demo-dashboard")
    demo_enabled = next(item for item in enabled if item["id"] == "webtrerm.demo-dashboard")

    assert demo_disabled["surfaces"]["pages"] == []
    assert demo_disabled["surfaces"]["studio_nodes"] == []
    assert demo_disabled["surfaces"]["agent_tools"] == []
    assert demo_disabled["surfaces"]["terminal_actions"] == []
    assert demo_disabled["surfaces"]["hooks"] == []
    assert demo_enabled["surfaces"]["pages"][0]["path"] == "/plugins/webtrerm.demo-dashboard/overview"
    assert demo_enabled["surfaces"]["studio_nodes"][0]["type"] == "plugin/webtrerm.demo-dashboard/demo-connector-ping"
    assert demo_enabled["surfaces"]["agent_tools"][0]["name"] == "plugin_webtrerm_demo_dashboard_ping"
    assert demo_enabled["surfaces"]["terminal_actions"][0]["id"] == "demo-terminal-ping"
    assert demo_enabled["surfaces"]["hooks"][0]["event"] == "plugin.demo.audit"


def test_active_plugin_surfaces_groups_enabled_surfaces():
    disabled = active_plugin_surfaces(set())
    enabled = active_plugin_surfaces({"webtrerm.demo-dashboard"})

    assert disabled["pages"] == []
    assert disabled["dashboard_widgets"] == []
    assert enabled["pages"][0]["plugin_id"] == "webtrerm.demo-dashboard"
    assert enabled["dashboard_widgets"][0]["id"] == "demo-health"


def test_manifest_validation_rejects_late_json_shape_errors():
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest["categories"] = "dashboard"

    with pytest.raises(PluginValidationError) as exc:
        validate_plugin_manifest(manifest)

    assert "categories must be a list" in str(exc.value)


def test_manifest_validation_rejects_invalid_action_risk():
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest["actions"][0]["risk_tier"] = "root"

    with pytest.raises(PluginValidationError) as exc:
        validate_plugin_manifest(manifest)

    assert "actions[0].risk_tier is invalid" in str(exc.value)


def test_local_plugin_package_validation_is_manifest_only(tmp_path):
    package = tmp_path / "demo-plugin.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(DEMO_PLUGIN_MANIFEST))
        archive.writestr("README.md", "demo")

    result = validate_wtp_package(package)

    assert result.ok is True
    assert result.plugin_id == "webtrerm.demo-dashboard"
    assert result.version == "0.1.0"
    assert result.file_count == 2
    assert result.static_scan.passed is True
    assert result.sbom["summary"]["file_count"] == 2
    assert result.sbom["summary"]["component_count"] == 0
    assert result.dependency_scan["passed"] is True


def test_local_plugin_package_validation_rejects_executable_entries(tmp_path):
    package = tmp_path / "bad-plugin.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(DEMO_PLUGIN_MANIFEST))
        archive.writestr("setup.py", "print('no')")

    result = validate_wtp_package(package)

    assert result.ok is False
    assert result.static_scan.passed is False
    assert any("Executable" in item for item in result.errors)
    assert any(item.code == "executable_entry" for item in result.static_scan.findings)
    assert result.dependency_scan["passed"] is False


def test_local_plugin_package_validation_records_dependency_manifest_sbom(tmp_path):
    package = tmp_path / "dependency-plugin.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(DEMO_PLUGIN_MANIFEST))
        archive.writestr("requirements.txt", "requests==2.32.0\n# comment\n")

    result = validate_wtp_package(package)

    assert result.ok is False
    assert result.sbom["summary"]["dependency_manifest_count"] == 1
    assert result.dependency_scan["summary"]["dependency_count"] == 1
    assert result.dependency_scan["dependencies"][0]["name"] == "requests"
    assert any(item["code"] == "dependency_manifest_not_allowed_no_code" for item in result.dependency_scan["blockers"])


@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST=[],
)
def test_sandboxed_plugin_package_blocks_dependencies_without_allowlist(tmp_path):
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.dependency-tool",
            "name": "Dependency Tool",
            "slug": "dependency-tool",
            "publisher": {"id": "acme", "name": "Acme"},
            "surfaces": {
                "agent_tools": [
                    {
                        "id": "dependency-echo",
                        "name": "acme_dependency_echo",
                        "title": "Dependency echo",
                        "executor_ref": "sandbox:backend/plugin.py:handle",
                        "tool_spec": {"category": "general", "risk": "read", "runner": "plugin"},
                    }
                ]
            },
        }
    )
    package = tmp_path / "dependency-tool.wtp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", "def handle(payload):\n    return {'ok': True}\n")
        archive.writestr("requirements.txt", "requests==2.32.0\n")

    result = validate_wtp_package(package)

    assert result.ok is False
    assert result.static_scan.passed is True
    assert result.dependency_scan["passed"] is False
    assert result.dependency_scan["policy"]["allowlist_count"] == 0
    assert any(item["code"] == "dependency_not_allowlisted" for item in result.dependency_scan["blockers"])


@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST=["python:requests"],
)
def test_sandboxed_plugin_package_accepts_allowlisted_dependencies(tmp_path):
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.allowed-dependency-tool",
            "name": "Allowed Dependency Tool",
            "slug": "allowed-dependency-tool",
            "publisher": {"id": "acme", "name": "Acme"},
            "surfaces": {
                "agent_tools": [
                    {
                        "id": "allowed-dependency-echo",
                        "name": "acme_allowed_dependency_echo",
                        "title": "Allowed dependency echo",
                        "executor_ref": "sandbox:backend/plugin.py:handle",
                        "tool_spec": {"category": "general", "risk": "read", "runner": "plugin"},
                    }
                ]
            },
        }
    )
    package = tmp_path / "allowed-dependency-tool.wtp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr("backend/plugin.py", "def handle(payload):\n    return {'ok': True}\n")
        archive.writestr("requirements.txt", "requests==2.32.0\n")

    result = validate_wtp_package(package)

    assert result.ok is True
    assert result.static_scan.passed is True
    assert result.dependency_scan["passed"] is True
    assert result.dependency_scan["policy"]["allowlist_count"] == 1
    assert result.dependency_scan["dependencies"][0]["name"] == "requests"


def test_plugin_developer_commands_scaffold_validate_pack_and_audit(tmp_path):
    source_dir = tmp_path / "sdk-demo"
    dist_dir = tmp_path / "dist"

    call_command("plugin_scaffold", "acme.sdk-demo", directory=str(source_dir), stdout=StringIO())

    source_validation = validate_plugin_source_dir(source_dir)
    assert source_validation.ok is True
    assert source_validation.plugin_id == "acme.sdk-demo"
    assert (source_dir / "README.md").exists()
    assert (source_dir / "backend" / "tests" / "README.md").exists()

    call_command("plugin_validate", str(source_dir), stdout=StringIO())
    call_command("plugin_pack", str(source_dir), output_dir=str(dist_dir), stdout=StringIO())

    packages = list(dist_dir.glob("*.wtp"))
    assert len(packages) == 1
    package_validation = validate_wtp_package(packages[0])
    assert package_validation.ok is True
    assert package_validation.plugin_id == "acme.sdk-demo"
    assert package_validation.static_scan.passed is True

    audit_output = StringIO()
    call_command("plugin_audit", str(packages[0]), as_json=True, stdout=audit_output)
    audit_payload = json.loads(audit_output.getvalue())
    assert audit_payload["target_type"] == "package"
    assert audit_payload["ok"] is True
    assert audit_payload["plugin_id"] == "acme.sdk-demo"


def test_plugin_scaffold_dashboard_template_creates_metadata_surfaces(tmp_path):
    source_dir = tmp_path / "dashboard-demo"

    call_command(
        "plugin_scaffold", "acme.dashboard-demo", directory=str(source_dir), template="dashboard", stdout=StringIO()
    )

    source_validation = validate_plugin_source_dir(source_dir)
    manifest = source_validation.manifest
    assert source_validation.ok is True
    assert manifest["surfaces"]["pages"][0]["id"] == "overview"
    assert manifest["surfaces"]["dashboard_widgets"][0]["id"] == "status-widget"
    assert not (source_dir / "backend" / "plugin.py").exists()


@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST=[],
)
def test_plugin_scaffold_agent_tool_template_creates_sandbox_executor(tmp_path):
    source_dir = tmp_path / "agent-tool-demo"
    dist_dir = tmp_path / "dist"

    call_command(
        "plugin_scaffold", "acme.agent-tool-demo", directory=str(source_dir), template="agent-tool", stdout=StringIO()
    )

    source_validation = validate_plugin_source_dir(source_dir)
    manifest = source_validation.manifest
    assert source_validation.ok is True
    assert manifest["surfaces"]["agent_tools"][0]["executor_ref"] == "sandbox:backend/plugin.py:handle"
    assert manifest["surfaces"]["agent_tools"][0]["required_permission"] == "acme.agent-tool-demo.execute"
    assert (source_dir / "backend" / "plugin.py").exists()

    call_command("plugin_pack", str(source_dir), output_dir=str(dist_dir), stdout=StringIO())
    packages = list(dist_dir.glob("*.wtp"))
    assert len(packages) == 1
    assert validate_wtp_package(packages[0]).ok is True


@pytest.mark.django_db
def test_local_plugin_package_installs_disabled(tmp_path):
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest["id"] = "acme.local-demo"
    manifest["slug"] = "local-demo"
    manifest["publisher"] = {"id": "acme", "name": "Acme"}
    package = tmp_path / "local-plugin.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))

    installation = install_local_package(package)

    assert installation.status == PluginInstallation.STATUS_DISABLED
    stored = PluginPackage.objects.get(plugin_id="acme.local-demo")
    assert stored.source == PluginPackage.SOURCE_LOCAL
    assert stored.sbom["summary"]["file_count"] == 1
    assert stored.dependency_scan["passed"] is True
    assert stored.provenance["retention"]["retained"] is True
    assert retained_package_exists(stored.provenance["retention"]) is True


@pytest.mark.django_db
@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
)
def test_sandboxed_backend_agent_tool_executes_from_retained_package(tmp_path):
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update(
        {
            "id": "acme.sandbox-tool",
            "name": "Sandbox Tool",
            "slug": "sandbox-tool",
            "publisher": {"id": "acme", "name": "Acme"},
            "surfaces": {
                "agent_tools": [
                    {
                        "id": "sandbox-echo",
                        "name": "acme_sandbox_echo",
                        "title": "Sandbox echo",
                        "description": "Runs in the backend sandbox worker.",
                        "executor_ref": "sandbox:backend/plugin.py:handle",
                        "params": {"message": {"type": "string", "required": False}},
                        "tool_spec": {
                            "category": "general",
                            "risk": "read",
                            "runner": "plugin",
                            "input_schema": {"message": {"type": "string", "required": False}},
                            "mutates_state": False,
                            "requires_verification": False,
                            "output_compactor": "tail",
                        },
                    }
                ]
            },
        }
    )
    package = tmp_path / "sandbox-tool.wtp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("webtrerm.plugin.json", json.dumps(manifest))
        archive.writestr(
            "backend/plugin.py",
            "def handle(payload):\n"
            "    args = payload['payload'].get('arguments', {})\n"
            "    return {'message': args.get('message', ''), 'surface': payload['payload'].get('surface')}\n",
        )

    validation = validate_wtp_package(package)
    assert validation.ok is True
    assert validation.static_scan.passed is True
    assert validation.dependency_scan["passed"] is True

    installation = install_local_package(package)
    stored = PluginPackage.objects.get(plugin_id="acme.sandbox-tool")
    stored.review_status = PluginPackage.REVIEW_VERIFIED
    stored.signature_status = PluginPackage.SIGNATURE_SIGNED
    stored.save(update_fields=["review_status", "signature_status", "updated_at"])
    installation = set_installation_status(installation.id, enable=True)
    assert installation.status == PluginInstallation.STATUS_ENABLED

    tool = next(item for item in active_agent_tools({"acme.sandbox-tool"}) if item["name"] == "acme_sandbox_echo")
    result = agent_tool_execution_provider({"tool": tool, "arguments": {"message": "hello sandbox"}})

    assert result["success"] is True
    assert result["result"]["message"] == "hello sandbox"
    assert result["result"]["surface"] == "agent_tool"
