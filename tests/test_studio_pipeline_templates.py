from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, PipelineTemplate
from studio.pipeline_validation import validate_pipeline_definition
from studio.services.pipeline_template_recommendations import (
    build_template_graph_patch,
    get_pilot_pipeline_template,
    recommend_pilot_pipeline_templates,
)
from studio.templates_data import PIPELINE_TEMPLATES

PILOT_TEMPLATE_SLUGS = {
    "pilot-kubernetes-rollout",
    "pilot-gitlab-failed-pipeline-mr",
    "pilot-database-diagnostics-maintenance",
    "pilot-observability-incident-response",
    "pilot-linux-package-maintenance",
    "pilot-linux-disk-cleanup",
    "pilot-backup-restore-check",
    "pilot-service-config-validate-restart",
}


def _pilot_templates() -> list[dict]:
    return [template for template in PIPELINE_TEMPLATES if template["slug"] in PILOT_TEMPLATE_SLUGS]


def test_pilot_ops_templates_are_registered_and_valid():
    user = User(username="template-validator", is_staff=True)
    templates = _pilot_templates()

    assert {template["slug"] for template in templates} == PILOT_TEMPLATE_SLUGS

    for template in templates:
        errors = validate_pipeline_definition(
            nodes=template["nodes"],
            edges=template["edges"],
            owner=user,
            graph_version=template.get("graph_version", CURRENT_PIPELINE_GRAPH_VERSION),
        )
        assert errors == [], template["slug"]

        node_types = {node["type"] for node in template["nodes"]}
        assert not any(
            node_type.startswith(("keycloak/", "kubernetes/", "gitlab/", "database/")) for node_type in node_types
        )


def test_pilot_ops_templates_have_approval_and_verification_shape():
    for template in _pilot_templates():
        nodes = {node["id"]: node for node in template["nodes"]}
        node_types = {node["type"] for node in template["nodes"]}
        approved_targets = {
            edge["target"]
            for edge in template["edges"]
            if edge.get("source") == "approval" and edge.get("sourceHandle") == "approved"
        }

        assert any(node_type.startswith("trigger/") for node_type in node_types), template["slug"]
        assert "output/report" in node_types, template["slug"]

        mutating_nodes = {
            node_id
            for node_id, node in nodes.items()
            if (
                node["type"] in {"ops/service_action", "ops/docker_action", "ops/process_action"}
                or (
                    node["type"] == "ops/package_action"
                    and str(node.get("data", {}).get("action") or "list_updates") != "list_updates"
                )
                or (
                    node["type"] == "ops/disk_cleanup"
                    and str(node.get("data", {}).get("action") or "inspect") != "inspect"
                )
                or (
                    node["type"] == "agent/mcp_call"
                    and str(node.get("data", {}).get("permission_mode") or "").upper() != "READ_ONLY"
                )
            )
        }
        if mutating_nodes:
            assert "logic/human_approval" in node_types, template["slug"]
            assert nodes["approval"]["data"]["manual_link_only"] is True
            assert mutating_nodes <= approved_targets, template["slug"]

        if template["slug"] == "pilot-service-config-validate-restart":
            assert {"ops/server_snapshot", "ops/service_action", "ops/http_check"} <= node_types
        elif template["slug"] == "pilot-linux-package-maintenance":
            assert {"ops/server_snapshot", "ops/package_action"} <= node_types
        elif template["slug"] == "pilot-linux-disk-cleanup":
            assert {"ops/disk_cleanup", "agent/llm_query"} <= node_types
        elif template["slug"] == "pilot-backup-restore-check":
            assert {"ops/backup_restore_check", "agent/llm_query"} <= node_types
        elif template["slug"] == "pilot-observability-incident-response":
            assert {"trigger/monitoring", "agent/mcp_call", "agent/llm_query"} <= node_types
        else:
            assert "agent/mcp_call" in node_types


def test_pilot_template_recommendations_match_ops_intents():
    service = recommend_pilot_pipeline_templates(
        user_message="Перезапусти nginx после проверки конфига и healthcheck",
        pipeline_name="Service maintenance",
    )
    assert service[0]["slug"] == "pilot-service-config-validate-restart"
    assert "ops/service_action" in service[0]["node_types"]

    packages = recommend_pilot_pipeline_templates(
        user_message="Обнови пакеты openssl curl после проверки package state и approval",
        pipeline_name="Linux package maintenance",
    )
    assert packages[0]["slug"] == "pilot-linux-package-maintenance"
    assert "ops/package_action" in packages[0]["node_types"]

    disk = recommend_pilot_pipeline_templates(
        user_message="Диск заполнен, проверь свободное место, очисти старые tmp файлы после approval и сделай report",
        pipeline_name="Disk cleanup",
    )
    assert disk[0]["slug"] == "pilot-linux-disk-cleanup"
    assert "ops/disk_cleanup" in disk[0]["node_types"]

    backup = recommend_pilot_pipeline_templates(
        user_message="Проверь backup /var/backups, свежесть и restore check latest archive без изменений",
        pipeline_name="Backup restore check",
    )
    assert backup[0]["slug"] == "pilot-backup-restore-check"
    assert "ops/backup_restore_check" in backup[0]["node_types"]

    incident = recommend_pilot_pipeline_templates(
        user_message="Grafana critical alert api latency: query Prometheus and Loki, create PagerDuty incident after approval and verify acknowledgement",
        pipeline_name="Observability incident response",
    )
    assert incident[0]["slug"] == "pilot-observability-incident-response"
    assert "trigger/monitoring" in incident[0]["node_types"]


def test_pilot_template_graph_patch_preserves_safety_shape():
    template = get_pilot_pipeline_template("pilot-gitlab-failed-pipeline-mr")
    graph_patch = build_template_graph_patch(template, assistant_context={})
    nodes = {node["ref"]: node for node in graph_patch["nodes"]}
    approved_targets = {
        edge["target"]
        for edge in graph_patch["edges"]
        if edge["source"] == "approval" and edge["source_handle"] == "approved"
    }

    assert nodes["webhook"]["type"] == "trigger/webhook"
    assert nodes["create_mr"]["type"] == "agent/mcp_call"
    assert nodes["create_mr"]["data"]["permission_mode"] == "ASSISTED"
    assert nodes["create_mr"]["data"]["capability_pack"] == "gitlab-ci-support"
    assert nodes["create_mr"]["data"]["operation_kind"] == "gitlab.merge_request.create"
    assert nodes["create_mr"]["data"]["requires_approval"] is True
    assert nodes["create_mr"]["data"]["input_schema"]["properties"]["project_id"]["type"] == "string"
    assert "create_mr" in approved_targets


@pytest.mark.django_db
def test_load_pipeline_templates_creates_pilot_ops_templates():
    user = User.objects.create_user(username="template-loader", password="x", is_staff=True)
    out = io.StringIO()

    call_command("load_pipeline_templates", "--force", stdout=out)

    loaded_slugs = set(PipelineTemplate.objects.filter(category="Pilot OPS").values_list("slug", flat=True))
    assert loaded_slugs >= PILOT_TEMPLATE_SLUGS

    template = PipelineTemplate.objects.get(slug="pilot-kubernetes-rollout")
    assert template.graph_version == CURRENT_PIPELINE_GRAPH_VERSION

    pipeline = template.instantiate_for_user(user)
    assert pipeline.owner == user
    assert pipeline.graph_version == CURRENT_PIPELINE_GRAPH_VERSION
    assert any(node["type"] == "logic/human_approval" for node in pipeline.nodes)
