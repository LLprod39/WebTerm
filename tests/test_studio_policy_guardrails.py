from itertools import count

import pytest
from django.contrib.auth.models import User

from studio.models import CURRENT_PIPELINE_GRAPH_VERSION
from studio.pipeline_validation import validate_pipeline_definition

pytestmark = pytest.mark.django_db

_OWNER_COUNTER = count(1)


def _node(node_id: str, node_type: str, data: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "position": {"x": 0, "y": 0}, "data": data or {}}


def _edge(source: str, target: str, handle: str = "out") -> dict:
    return {"id": f"{source}-{target}-{handle}", "source": source, "target": target, "sourceHandle": handle}


def _validate(nodes: list[dict], edges: list[dict]) -> list[str]:
    owner = User.objects.create_user(username=f"policy-owner-{next(_OWNER_COUNTER)}", password="x", is_staff=True)
    return validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )


def test_policy_blocks_mutating_mcp_call_without_approval_path():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node(
                "grant",
                "agent/mcp_call",
                {
                    "tool_name": "keycloak_apply_access_change",
                    "mutates_state": True,
                    "permission_mode": "ASSISTED",
                },
            ),
            _node("report", "output/report"),
        ],
        [_edge("manual", "grant"), _edge("grant", "report", "success")],
    )

    assert any("Policy guard" in error and "grant" in error for error in errors)


def test_policy_allows_mutating_mcp_call_after_approved_human_gate():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("approval", "logic/human_approval", {"manual_link_only": True}),
            _node("grant", "agent/mcp_call", {"tool_name": "keycloak_apply_access_change", "mutates_state": True}),
            _node("report", "output/report"),
        ],
        [
            _edge("manual", "approval"),
            _edge("approval", "grant", "approved"),
            _edge("grant", "report", "success"),
        ],
    )

    assert not [error for error in errors if "Policy guard" in error]


def test_policy_rejects_mutating_node_when_one_merge_path_skips_approval():
    errors = _validate(
        [
            _node("manual_a", "trigger/manual"),
            _node("manual_b", "trigger/manual"),
            _node("approval", "logic/human_approval", {"manual_link_only": True}),
            _node("merge", "logic/merge", {"mode": "all"}),
            _node("restart", "ops/service_action", {"action": "restart", "service": "nginx"}),
            _node("report", "output/report"),
        ],
        [
            _edge("manual_a", "approval"),
            _edge("approval", "merge", "approved"),
            _edge("manual_b", "merge"),
            _edge("merge", "restart"),
            _edge("restart", "report", "success"),
        ],
    )

    assert any("Policy guard" in error and "restart" in error for error in errors)


def test_policy_blocks_mutating_ssh_command_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("ssh", "agent/ssh_cmd", {"command": "systemctl restart nginx"}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "ssh"), _edge("ssh", "report", "success")],
    )

    assert any("Policy guard" in error and "ssh" in error for error in errors)


def test_policy_blocks_file_write_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("write_config", "ops/file_action", {"action": "write", "path": "/etc/app/app.conf", "content": "x"}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "write_config"), _edge("write_config", "report", "success")],
    )

    assert any("Policy guard" in error and "write_config" in error for error in errors)


def test_policy_allows_file_read_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("read_config", "ops/file_action", {"action": "read", "path": "/etc/os-release"}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "read_config"), _edge("read_config", "report", "success")],
    )

    assert not [error for error in errors if "Policy guard" in error]


def test_policy_blocks_package_mutation_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("install_pkg", "ops/package_action", {"action": "install", "packages": ["curl"]}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "install_pkg"), _edge("install_pkg", "report", "success")],
    )

    assert any("Policy guard" in error and "install_pkg" in error for error in errors)


def test_policy_allows_package_update_listing_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("list_pkgs", "ops/package_action", {"action": "list_updates"}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "list_pkgs"), _edge("list_pkgs", "report", "success")],
    )

    assert not [error for error in errors if "Policy guard" in error]


def test_validation_rejects_mcp_call_missing_required_schema_arguments():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node(
                "inspect",
                "agent/mcp_call",
                {
                    "tool_name": "kubernetes_describe_workload",
                    "permission_mode": "READ_ONLY",
                    "arguments": {"namespace": "auth"},
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "kind": {"type": "string", "enum": ["deployment", "statefulset"]},
                            "name": {"type": "string"},
                        },
                        "required": ["namespace", "kind", "name"],
                    },
                },
            ),
            _node("report", "output/report"),
        ],
        [_edge("manual", "inspect"), _edge("inspect", "report", "success")],
    )

    assert any("MCP argument 'kind' is required" in error for error in errors)
    assert any("MCP argument 'name' is required" in error for error in errors)


def test_validation_checks_mcp_call_schema_enum_and_allows_placeholders():
    ok_errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node(
                "inspect",
                "agent/mcp_call",
                {
                    "tool_name": "kubernetes_describe_workload",
                    "permission_mode": "READ_ONLY",
                    "arguments": {"namespace": "{namespace}", "kind": "{kind}", "name": "{workload_name}"},
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "kind": {"type": "string", "enum": ["deployment", "statefulset"]},
                            "name": {"type": "string"},
                        },
                        "required": ["namespace", "kind", "name"],
                    },
                },
            ),
            _node("report", "output/report"),
        ],
        [_edge("manual", "inspect"), _edge("inspect", "report", "success")],
    )
    assert not [error for error in ok_errors if "MCP argument" in error]

    bad_errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node(
                "inspect",
                "agent/mcp_call",
                {
                    "tool_name": "kubernetes_describe_workload",
                    "permission_mode": "READ_ONLY",
                    "arguments": {"namespace": "auth", "kind": "cronjob", "name": "worker"},
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "kind": {"type": "string", "enum": ["deployment", "statefulset"]},
                            "name": {"type": "string"},
                        },
                        "required": ["namespace", "kind", "name"],
                    },
                },
            ),
            _node("report", "output/report"),
        ],
        [_edge("manual", "inspect"), _edge("inspect", "report", "success")],
    )
    assert any("MCP argument 'kind' must be one of" in error for error in bad_errors)


def test_policy_blocks_disk_cleanup_mutation_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("cleanup", "ops/disk_cleanup", {"action": "tmp_cleanup", "min_age_days": 7}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "cleanup"), _edge("cleanup", "report", "success")],
    )

    assert any("Policy guard" in error and "cleanup" in error for error in errors)


def test_policy_allows_disk_inspect_without_approval():
    errors = _validate(
        [
            _node("manual", "trigger/manual"),
            _node("disk", "ops/disk_cleanup", {"action": "inspect"}),
            _node("report", "output/report"),
        ],
        [_edge("manual", "disk"), _edge("disk", "report", "success")],
    )

    assert not [error for error in errors if "Policy guard" in error]
