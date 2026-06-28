import copy
import json

from django.test import override_settings

from app.plugins.catalog import DEMO_PLUGIN_MANIFEST
from plugin_marketplace.services.developer_package_service import validate_plugin_source_dir


def _write_sandbox_dependency_source(source_dir):
    manifest = copy.deepcopy(DEMO_PLUGIN_MANIFEST)
    manifest.update({
        "id": "acme.source-dependency-tool",
        "name": "Source Dependency Tool",
        "slug": "source-dependency-tool",
        "publisher": {"id": "acme", "name": "Acme"},
        "surfaces": {
            "agent_tools": [
                {
                    "id": "source-dependency-echo",
                    "name": "acme_source_dependency_echo",
                    "title": "Source dependency echo",
                    "executor_ref": "sandbox:backend/plugin.py:handle",
                    "tool_spec": {"category": "general", "risk": "read", "runner": "plugin"},
                }
            ]
        },
    })
    (source_dir / "backend").mkdir(parents=True)
    (source_dir / "webtrerm.plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source_dir / "backend" / "plugin.py").write_text("def handle(payload):\n    return {'ok': True}\n", encoding="utf-8")
    (source_dir / "requirements.txt").write_text("requests==2.32.0\n", encoding="utf-8")


@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST=[],
)
def test_source_validation_blocks_sandbox_dependencies_without_allowlist(tmp_path):
    source_dir = tmp_path / "source-dependency-tool"
    _write_sandbox_dependency_source(source_dir)

    result = validate_plugin_source_dir(source_dir)

    assert result.ok is False
    assert any("dependency_not_allowlisted" in error for error in result.errors)


@override_settings(
    PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES=True,
    PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED=True,
    PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST=["python:requests"],
)
def test_source_validation_accepts_allowlisted_sandbox_dependencies(tmp_path):
    source_dir = tmp_path / "source-dependency-tool"
    _write_sandbox_dependency_source(source_dir)

    result = validate_plugin_source_dir(source_dir)

    assert result.ok is True
