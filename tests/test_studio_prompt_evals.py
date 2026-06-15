from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from django.contrib.auth.models import User
from django.test import Client

import pytest

from core_ui.models import UserAppPermission
from servers.models import Server
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, MCPServerPool
from studio.pipeline_validation import validate_pipeline_definition
from studio.services.pipeline_template_recommendations import (
    PILOT_TEMPLATE_SLUGS,
    build_template_graph_patch,
    build_template_resource_plan,
    get_pilot_pipeline_template,
    recommend_pilot_pipeline_templates,
)
from studio.views.pipeline_assistant_preview import apply_pipeline_assistant_patch, pipeline_assistant_risk

EVAL_FIXTURE = Path(__file__).parent / "fixtures" / "studio_ops_prompt_evals.json"
SERVICE_SPECIFIC_PREFIXES = ("keycloak/", "kubernetes/", "gitlab/", "database/", "postgres/", "mysql/")
MUTATING_OPS_TYPES = {"ops/service_action", "ops/docker_action", "ops/process_action"}


def _load_eval_cases() -> list[dict[str, Any]]:
    return json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))


EVAL_CASES = _load_eval_cases()


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _node_data(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data")
    return data if isinstance(data, dict) else {}


def _node_label(node: dict[str, Any]) -> str:
    data = _node_data(node)
    return str(data.get("label") or node.get("id") or "").lower()


def _is_read_stage(node: dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "")
    data = _node_data(node)
    if node_type == "ops/server_snapshot":
        return True
    if node_type == "ops/package_action" and str(data.get("action") or "list_updates") == "list_updates":
        return True
    if node_type == "ops/disk_cleanup" and str(data.get("action") or "inspect") == "inspect":
        return True
    if node_type == "ops/backup_restore_check":
        return True
    return node_type == "agent/mcp_call" and str(data.get("permission_mode") or "").upper() == "READ_ONLY"


def _is_mutating_node(node: dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "")
    data = _node_data(node)
    if node_type in MUTATING_OPS_TYPES:
        return True
    if node_type == "ops/file_action":
        return str(data.get("action") or "read") == "write"
    if node_type == "ops/package_action":
        return str(data.get("action") or "list_updates") != "list_updates"
    if node_type == "ops/disk_cleanup":
        return str(data.get("action") or "inspect") != "inspect"
    if node_type == "ops/backup_restore_check":
        return False
    return node_type == "agent/mcp_call" and str(data.get("permission_mode") or "").upper() != "READ_ONLY"


def _is_verification_node(node: dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "")
    data = _node_data(node)
    label = _node_label(node)
    if node_type == "ops/http_check":
        return True
    if node_type == "ops/package_action" and str(data.get("action") or "list_updates") == "list_updates":
        return True
    if node_type == "ops/disk_cleanup" and str(data.get("action") or "inspect") == "inspect":
        return True
    if node_type == "ops/backup_restore_check" and str(data.get("action") or "inspect") == "verify_latest":
        return True
    return (
        node_type == "agent/mcp_call"
        and str(data.get("permission_mode") or "").upper() == "READ_ONLY"
        and ("verify" in label or "health" in label)
    )


def _edge_handle(edge: dict[str, Any]) -> str:
    return str(edge.get("sourceHandle") or edge.get("source_handle") or "out")


def _has_path(
    *,
    start: str,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> bool:
    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source and target:
            outgoing.setdefault(source, []).append(target)

    visited: set[str] = set()
    stack = list(outgoing.get(start, []))
    while stack:
        node_id = stack.pop()
        if node_id in visited:
            continue
        visited.add(node_id)
        node = nodes.get(node_id)
        if node and predicate(node):
            return True
        stack.extend(outgoing.get(node_id, []))
    return False


def _assert_mutations_are_approved(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]], case_id: str) -> None:
    mutating_ids = {node_id for node_id, node in nodes.items() if _is_mutating_node(node)}
    if not mutating_ids:
        return

    approved_targets = {
        str(edge.get("target") or "")
        for edge in edges
        if _edge_handle(edge) == "approved"
        and nodes.get(str(edge.get("source") or ""), {}).get("type") == "logic/human_approval"
    }
    assert mutating_ids <= approved_targets, f"{case_id}: mutating nodes without approval edge: {mutating_ids - approved_targets}"


def _assert_verification_and_report_paths(nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]], case_id: str) -> None:
    mutating_ids = {node_id for node_id, node in nodes.items() if _is_mutating_node(node)}
    if not mutating_ids:
        assert any(_is_verification_node(node) for node in nodes.values()), f"{case_id}: read-only workflow has no verification node"
        assert any(str(node.get("type") or "").startswith("output/") for node in nodes.values()), f"{case_id}: read-only workflow has no report"
        return
    for node_id in mutating_ids:
        assert _has_path(start=node_id, nodes=nodes, edges=edges, predicate=_is_verification_node), (
            f"{case_id}: mutating node '{node_id}' has no verification path"
        )
        assert _has_path(start=node_id, nodes=nodes, edges=edges, predicate=lambda node: str(node.get("type") or "").startswith("output/")), (
            f"{case_id}: mutating node '{node_id}' has no report/notification path"
        )


def test_ops_prompt_eval_fixture_covers_pilot_launch_distribution():
    assert len(EVAL_CASES) == 35
    expected_templates = {case["expected_template"] for case in EVAL_CASES}
    assert expected_templates == PILOT_TEMPLATE_SLUGS

    by_template = Counter(case["expected_template"] for case in EVAL_CASES)
    assert by_template["pilot-keycloak-access-change"] >= 5
    assert by_template["pilot-observability-incident-response"] >= 5
    assert by_template["pilot-linux-package-maintenance"] >= 5
    assert by_template["pilot-linux-disk-cleanup"] >= 5
    assert by_template["pilot-backup-restore-check"] >= 5
    assert sum(count for slug, count in by_template.items() if slug != "pilot-keycloak-access-change") >= 30


def test_ops_prompt_evals_select_valid_safe_pilot_skeletons():
    owner = User(username="prompt-eval-owner", is_staff=True)

    for case in EVAL_CASES:
        recommendations = recommend_pilot_pipeline_templates(
            user_message=case["prompt"],
            pipeline_name=case["pipeline_name"],
            limit=3,
        )
        assert recommendations, f"{case['id']}: no template recommendation"
        assert recommendations[0]["slug"] == case["expected_template"], (
            f"{case['id']}: expected {case['expected_template']}, got {recommendations[0]['slug']}"
        )

        template = get_pilot_pipeline_template(recommendations[0]["slug"])
        assert template is not None, f"{case['id']}: missing template {recommendations[0]['slug']}"
        graph_patch = build_template_graph_patch(template, assistant_context={})
        preview_nodes, preview_edges = apply_pipeline_assistant_patch([], [], {"graph_patch": graph_patch})

        validation_errors = validate_pipeline_definition(
            nodes=preview_nodes,
            edges=preview_edges,
            owner=owner,
            graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
        )
        assert validation_errors == [], f"{case['id']}: {validation_errors}"

        nodes = {str(node.get("id") or ""): node for node in preview_nodes}
        node_types = {str(node.get("type") or "") for node in preview_nodes}
        assert set(case["must_have_node_types"]) <= node_types, (
            f"{case['id']}: missing node types {set(case['must_have_node_types']) - node_types}"
        )
        assert not any(node_type.startswith(SERVICE_SPECIFIC_PREFIXES) for node_type in node_types), (
            f"{case['id']}: service-specific node type leaked: {node_types}"
        )
        assert any(node_type.startswith("trigger/") for node_type in node_types), f"{case['id']}: no trigger"
        assert any(_is_read_stage(node) for node in preview_nodes), f"{case['id']}: no read/snapshot stage"
        assert "agent/llm_query" in node_types, f"{case['id']}: no AI analysis/planning stage"
        if any(_is_mutating_node(node) for node in preview_nodes):
            assert "logic/human_approval" in node_types, f"{case['id']}: no approval stage"
        assert any(node_type.startswith("output/") for node_type in node_types), f"{case['id']}: no report stage"

        _assert_mutations_are_approved(nodes, preview_edges, case["id"])
        _assert_verification_and_report_paths(nodes, preview_edges, case["id"])


def _build_bound_nodes(template_slug: str, prompt: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    template = get_pilot_pipeline_template(template_slug)
    assert template is not None
    context = {"binding_query": prompt, "pipeline_name": "", "user_message": prompt}
    graph_patch = build_template_graph_patch(template, assistant_context=context)
    return {str(node["ref"]): node for node in graph_patch["nodes"]}, build_template_resource_plan(
        template,
        assistant_context=context,
    )


def test_pilot_template_binding_fills_clear_keycloak_and_kubernetes_arguments():
    keycloak_nodes, keycloak_plan = _build_bound_nodes(
        "pilot-keycloak-access-change",
        "Keycloak realm master: добавить роль admin пользователю ivan.petrov в группу devops",
    )
    apply_args = keycloak_nodes["apply_change"]["data"]["arguments"]
    assert apply_args["realm"] == "master"
    assert apply_args["username"] == "ivan.petrov"
    assert apply_args["role"] == "admin"
    assert apply_args["group"] == "devops"
    assert apply_args["operation"] == "add"
    assert "Argument: realm" not in keycloak_plan["missing"]
    assert "Argument: username" not in keycloak_plan["missing"]

    kubernetes_nodes, kubernetes_plan = _build_bound_nodes(
        "pilot-kubernetes-rollout",
        "K8s cluster prod namespace payments rollout restart deployment api-gateway",
    )
    inspect_args = kubernetes_nodes["inspect"]["data"]["arguments"]
    assert inspect_args["cluster"] == "prod"
    assert inspect_args["namespace"] == "payments"
    assert inspect_args["kind"] == "deployment"
    assert inspect_args["name"] == "api-gateway"
    assert "Argument: namespace" not in kubernetes_plan["missing"]
    assert "Argument: workload_name" not in kubernetes_plan["missing"]
    assert "Skill: kubernetes-safety" in kubernetes_plan["missing"]


def test_pilot_template_binding_handles_gitlab_service_and_missing_arguments():
    gitlab_nodes, gitlab_plan = _build_bound_nodes(
        "pilot-gitlab-failed-pipeline-mr",
        "GitLab project 42 pipeline 987 branch release/2.1 commit deadbeef failed",
    )
    inspect_args = gitlab_nodes["inspect"]["data"]["arguments"]
    create_args = gitlab_nodes["create_mr"]["data"]["arguments"]
    assert inspect_args["project_id"] == "42"
    assert inspect_args["pipeline_id"] == "987"
    assert inspect_args["commit_sha"] == "deadbeef"
    assert create_args["target_branch"] == "release/2.1"
    assert create_args["source_branch"] == "ops-fix/987"
    assert "Argument: project_id" not in gitlab_plan["missing"]

    service_nodes, service_plan = _build_bound_nodes(
        "pilot-service-config-validate-restart",
        "Проверить конфиг nginx на web-prod-01, перезапустить сервис и проверить https://web-prod-01/health",
    )
    assert service_nodes["restart"]["data"]["service"] == "nginx"
    assert service_nodes["http_check"]["data"]["url"] == "https://web-prod-01/health"
    assert "Argument: healthcheck_url" not in service_plan["missing"]

    package_nodes, package_plan = _build_bound_nodes(
        "pilot-linux-package-maintenance",
        "Update packages openssl curl ca-certificates on server web-prod-01 after approval",
    )
    assert package_nodes["apply_updates"]["data"]["packages"] == "openssl,curl,ca-certificates"
    assert package_nodes["apply_updates"]["data"]["action"] == "update"
    assert "Argument: packages" not in package_plan["missing"]

    backup_nodes, backup_plan = _build_bound_nodes(
        "pilot-backup-restore-check",
        "Check backup path /var/backups max age 24 hours and verify latest archive",
    )
    assert backup_nodes["inspect_backup"]["data"]["path"] == "/var/backups"
    assert backup_nodes["verify_latest"]["data"]["path"] == "/var/backups"
    assert "Argument: backup_path" not in backup_plan["missing"]

    incident_nodes, incident_plan = _build_bound_nodes(
        "pilot-observability-incident-response",
        "Grafana critical alert alert-42 for service billing-api: query Prometheus/Loki and create incident ticket after approval",
    )
    context_args = incident_nodes["alert_context"]["data"]["arguments"]
    ticket_args = incident_nodes["ticket"]["data"]["arguments"]
    assert context_args["alert_id"] == "alert-42"
    assert context_args["alert_source"] == "Grafana"
    assert context_args["service"] == "billing-api"
    assert context_args["severity"] == "critical"
    assert context_args["time_range_minutes"] == 60
    assert ticket_args["severity"] == "critical"
    assert "Argument: alert_id" not in incident_plan["missing"]
    assert "Argument: service_name" not in incident_plan["missing"]

    incomplete_nodes, incomplete_plan = _build_bound_nodes(
        "pilot-keycloak-access-change",
        "Keycloak: add realm role finance-auditor to user ivan.petrov",
    )
    incomplete_args = incomplete_nodes["apply_change"]["data"]["arguments"]
    assert incomplete_args["realm"] == "{realm}"
    assert incomplete_args["role"] == "finance-auditor"
    assert incomplete_args["username"] == "ivan.petrov"
    assert "Argument: realm" in incomplete_plan["missing"]
    assert "Argument: group" in incomplete_plan["missing"]


def test_backend_risk_uses_mcp_capability_metadata_not_only_tool_name_regex():
    risk = pipeline_assistant_risk(
        [
            {
                "id": "custom_mutation",
                "type": "agent/mcp_call",
                "data": {
                    "label": "Apply custom change",
                    "tool_name": "tenant_transition",
                    "permission_mode": "ASSISTED",
                    "operation_kind": "internal.tenant.transition",
                    "mutates_state": True,
                    "requires_approval": True,
                },
            }
        ]
    )

    assert risk["level"] == "review"
    assert risk["items"][0]["node_id"] == "custom_mutation"
    assert "mcp_mutation" in risk["items"][0]["categories"]
    assert "Tool metadata requires human approval." in risk["items"][0]["reasons"]


@pytest.mark.django_db
def test_ops_prompt_evals_create_valid_provider_free_drafts(monkeypatch):
    user = User.objects.create_user(username="prompt-eval-compiler", password="x", is_staff=True)
    _grant_feature(user, "studio_pipelines", "studio_mcp", "studio_skills")
    Server.objects.create(user=user, name="web-prod-01", host="10.0.0.50", username="root")
    for name, description in (
        ("Keycloak Admin", "Keycloak IAM users, groups, realms and roles"),
        ("Kubernetes MCP", "Kubernetes workload diagnostics and rollout operations"),
        ("GitLab MCP", "GitLab merge request and CI pipeline automation"),
        ("Database MCP", "Database diagnostics and guarded maintenance"),
        ("Observability MCP", "Grafana Prometheus Loki PagerDuty Jira incident response automation"),
    ):
        MCPServerPool.objects.create(
            owner=user,
            name=name,
            description=description,
            transport=MCPServerPool.TRANSPORT_STDIO,
        )

    provider_calls: list[str] = []

    async def fail_if_provider_called(self, prompt: str, model: str = "auto", purpose: str = "chat", **kwargs):
        provider_calls.append(prompt)
        yield json.dumps({"error": "LLM provider must not be called by deterministic compiler mode"})

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fail_if_provider_called, raising=False)

    client = Client()
    client.force_login(user)

    for case in EVAL_CASES:
        response = client.post(
            "/api/studio/assistant/drafts/",
            data=json.dumps(
                {
                    "pipeline_name": case["pipeline_name"],
                    "nodes": [],
                    "edges": [],
                    "user_message": case["prompt"],
                    "intent": "create",
                    "compiler_mode": "deterministic",
                    "draft_mode": True,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 201, f"{case['id']}: {response.content!r}"
        draft = response.json()
        revision = draft["latest_revision"]
        assistant_response = revision["response"]
        preview_nodes = revision["preview_nodes"]
        preview_edges = revision["preview_edges"]
        nodes = {str(node.get("id") or ""): node for node in preview_nodes}
        node_types = {str(node.get("type") or "") for node in preview_nodes}

        assert draft["status"] == ("needs_input" if assistant_response.get("questions") else "ready"), case["id"]
        assert assistant_response["selected_template"]["slug"] == case["expected_template"], case["id"]
        assert assistant_response["selected_template"]["source"] == "pilot_template_compiler", case["id"]
        assert assistant_response["validation"]["ok"] is True, case["id"]
        assert assistant_response["risk"]["level"] != "dangerous", case["id"]
        assert set(case["must_have_node_types"]) <= node_types, case["id"]
        assert not any(node_type.startswith(SERVICE_SPECIFIC_PREFIXES) for node_type in node_types), case["id"]
        assert any(node_type.startswith("trigger/") for node_type in node_types), case["id"]
        assert any(_is_read_stage(node) for node in preview_nodes), case["id"]
        assert any(node_type.startswith("output/") for node_type in node_types), case["id"]
        if any(_is_mutating_node(node) for node in preview_nodes):
            assert "logic/human_approval" in node_types, case["id"]
        _assert_mutations_are_approved(nodes, preview_edges, case["id"])
        _assert_verification_and_report_paths(nodes, preview_edges, case["id"])

    assert provider_calls == []
