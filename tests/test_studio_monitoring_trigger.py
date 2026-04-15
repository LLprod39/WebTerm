from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server, ServerAlert
from servers.monitor import _create_alerts
from studio.docker_service_recovery import (
    _build_container_verify_command,
    ensure_docker_service_recovery_pipeline,
)
from studio.models import Pipeline, PipelineRun
from studio.pipeline_validation import validate_pipeline_definition
from studio.trigger_dispatch import launch_monitoring_triggers_for_alert, monitoring_trigger_matches_alert

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _disable_signal_launch(monkeypatch):
    monkeypatch.setattr("servers.signals._launch_monitoring_pipelines", lambda _alert_id: None)


def test_validation_accepts_nested_monitoring_filters():
    owner = User.objects.create_user(username="monitoring-validator", password="x")
    server = Server.objects.create(user=owner, name="monitor-srv", host="10.0.0.15", username="root")

    nodes = [
        {
            "id": "monitoring_start",
            "type": "trigger/monitoring",
            "position": {"x": 0, "y": 0},
            "data": {
                "label": "Monitoring",
                "monitoring_filters": {
                    "server_ids": [server.id],
                    "severities": ["critical"],
                    "alert_types": ["service"],
                    "container_names": ["mini-prod-mcp-demo"],
                },
            },
        },
        {
            "id": "report",
            "type": "output/report",
            "position": {"x": 120, "y": 0},
            "data": {"template": "ok"},
        },
    ]
    edges = [{"id": "e1", "source": "monitoring_start", "target": "report", "sourceHandle": "out"}]

    errors = validate_pipeline_definition(nodes=nodes, edges=edges, owner=owner, graph_version=2)

    assert errors == []


def test_sync_triggers_from_nodes_merges_monitoring_filters_from_node_data():
    owner = User.objects.create_user(username="monitoring-sync", password="x")
    server = Server.objects.create(user=owner, name="monitor-srv", host="10.0.0.20", username="root")
    pipeline = Pipeline.objects.create(
        owner=owner,
        name="Monitoring Sync Pipeline",
        graph_version=2,
        nodes=[
            {
                "id": "monitoring_start",
                "type": "trigger/monitoring",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": "Monitoring",
                    "server_ids": [server.id],
                    "severities": ["critical"],
                    "alert_types": ["service"],
                    "container_names": ["mini-prod-mcp-demo"],
                    "match_text": "docker-down",
                },
            }
        ],
        edges=[],
    )

    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(node_id="monitoring_start")

    assert trigger.monitoring_filters == {
        "server_ids": [server.id],
        "severities": ["critical"],
        "alert_types": ["service"],
        "container_names": ["mini-prod-mcp-demo"],
        "match_text": "docker-down",
    }


def test_monitoring_trigger_matches_alert_by_container_name():
    owner = User.objects.create_user(username="monitoring-match", password="x")
    server = Server.objects.create(user=owner, name="docker-srv", host="10.0.0.16", username="root")
    pipeline = ensure_docker_service_recovery_pipeline(
        owner,
        server_id=server.id,
        container_name="mini-prod-mcp-demo",
        name="Monitoring Match Pipeline",
    )
    trigger = pipeline.triggers.get(trigger_type="monitoring")

    matching_alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Docker-контейнер недоступен: mini-prod-mcp-demo",
        message="mini-prod-mcp-demo: exited",
        metadata={
            "service_kind": "docker_container",
            "container_name": "mini-prod-mcp-demo",
            "containers": [{"name": "mini-prod-mcp-demo", "state": "exited", "status": "Exited (1) 10s ago"}],
        },
    )
    non_matching_alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Docker-контейнер недоступен: other-service",
        message="other-service: exited",
        metadata={
            "service_kind": "docker_container",
            "container_name": "other-service",
            "containers": [{"name": "other-service", "state": "exited", "status": "Exited (1) 10s ago"}],
        },
    )

    assert monitoring_trigger_matches_alert(trigger, matching_alert) is True
    assert monitoring_trigger_matches_alert(trigger, non_matching_alert) is False


def test_docker_recovery_pipeline_builder_contains_ai_recovery_flow():
    owner = User.objects.create_user(username="monitoring-builder", password="x")
    server = Server.objects.create(user=owner, name="docker-srv", host="10.0.0.18", username="root")
    pipeline = ensure_docker_service_recovery_pipeline(
        owner,
        server_id=server.id,
        container_name="mini-prod-mcp-demo",
        name="Monitoring Builder Pipeline",
    )

    errors = validate_pipeline_definition(
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=owner,
        graph_version=pipeline.graph_version,
    )
    node_ids = {str(node.get("id") or "") for node in pipeline.nodes}

    assert errors == []
    assert {
        "monitoring_start",
        "investigate_agent",
        "plan_llm",
        "approval_gate",
        "recovery_agent",
        "operator_input_1",
        "guided_recovery_1",
        "operator_input_2",
        "guided_recovery_2",
    }.issubset(node_ids)

    nodes_by_id = {str(node.get("id") or ""): node for node in pipeline.nodes}
    approval_message = str(nodes_by_id["approval_gate"]["data"]["telegram_message"])
    operator_message_1 = str(nodes_by_id["operator_input_1"]["data"]["message"])
    operator_message_2 = str(nodes_by_id["operator_input_2"]["data"]["message"])
    success_message = str(nodes_by_id["success_telegram"]["data"]["message"])
    failure_message = str(nodes_by_id["final_failure_telegram"]["data"]["message"])

    assert "{plan_report_output}" not in approval_message
    assert "{plan_llm_output}" in approval_message
    assert "{all_outputs}" not in operator_message_1
    assert "{all_outputs}" not in operator_message_2
    assert "{verify_after_recovery_output}" in operator_message_1
    assert "{verify_after_guidance_1_output}" in operator_message_2
    assert "{success_report_output}" not in success_message
    assert "{final_failure_report_output}" not in failure_message


def test_docker_recovery_verify_command_survives_python_formatting():
    command = _build_container_verify_command("mini-prod-mcp-demo")

    rendered = command.format()

    assert "{{.State.Status}}" in rendered
    assert "{{if .State.Health}}" in rendered
    assert "{{.State.Health.Status}}" in rendered
    assert "{{else}}" in rendered
    assert "{{end}}" in rendered


def test_launch_monitoring_triggers_creates_run_with_entry_node(monkeypatch):
    owner = User.objects.create_user(username="monitoring-launch", password="x")
    server = Server.objects.create(user=owner, name="docker-srv", host="10.0.0.17", username="root")
    pipeline = ensure_docker_service_recovery_pipeline(
        owner,
        server_id=server.id,
        container_name="mini-prod-mcp-demo",
        name="Monitoring Launch Pipeline",
    )

    launched_run_ids: list[int] = []

    def fake_launch(run):
        launched_run_ids.append(run.id)

    monkeypatch.setattr("studio.trigger_dispatch.launch_pipeline_run_async", fake_launch)

    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Docker-контейнер недоступен: mini-prod-mcp-demo",
        message="mini-prod-mcp-demo: unhealthy",
        metadata={
            "service_kind": "docker_container",
            "container_name": "mini-prod-mcp-demo",
            "containers": [{"name": "mini-prod-mcp-demo", "state": "running", "status": "Up 2m (unhealthy)"}],
        },
    )

    runs = launch_monitoring_triggers_for_alert(alert)

    assert len(runs) == 1
    run = runs[0]
    assert run.id in launched_run_ids
    assert run.pipeline_id == pipeline.id
    assert run.entry_node_id == "monitoring_start"
    assert run.trigger is not None
    assert run.trigger.trigger_type == "monitoring"
    assert run.context["container_name"] == "mini-prod-mcp-demo"
    assert run.context["server_id"] == server.id
    stored_run = PipelineRun.objects.get(pk=run.pk)
    assert stored_run.trigger_data["source"] == "monitoring"


def test_create_alerts_resolves_stale_docker_alert_when_container_recovers():
    owner = User.objects.create_user(username="monitoring-resolve", password="x")
    server = Server.objects.create(user=owner, name="docker-srv", host="10.0.0.21", username="root")
    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Docker-контейнер недоступен: mini-prod-mcp-demo",
        message="mini-prod-mcp-demo: exited",
        metadata={
            "service_kind": "docker_container",
            "container_name": "mini-prod-mcp-demo",
            "fingerprint": "docker-down:mini-prod-mcp-demo",
            "containers": [{"name": "mini-prod-mcp-demo", "state": "exited", "status": "Exited (137) 20s ago"}],
        },
    )

    async_to_sync(_create_alerts)(
        server,
        {},
        {
            "docker": {
                "containers": [{"name": "mini-prod-mcp-demo", "state": "running", "status": "Up 3m"}],
                "problem_containers": [],
            }
        },
    )

    alert.refresh_from_db()
    assert alert.is_resolved is True
    assert alert.resolved_at is not None
