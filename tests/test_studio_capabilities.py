import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Server
from studio.capability_registry import build_studio_capability_registry
from studio.models import MCPServerPool


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


pytestmark = pytest.mark.django_db


def test_capability_registry_maps_keycloak_to_mcp_skill_and_universal_nodes():
    user = User.objects.create_user(username="cap-admin", password="x", is_staff=True)
    Server.objects.create(user=user, name="ops-srv", host="10.0.0.10", username="root")
    mcp = MCPServerPool.objects.create(
        owner=user,
        name="Keycloak Admin",
        description="Manage Keycloak users, groups, roles, realms and clients",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:8766/mcp",
    )

    registry = build_studio_capability_registry(user, server_count=1)

    assert registry["strategy"]["mode"] == "minimal_universal_nodes"
    assert registry["strategy"]["default_execution_node"] == "agent/mcp_call"
    assert any(node["type"] == "agent/mcp_call" for node in registry["nodes"])
    assert any(node["type"] == "logic/human_approval" for node in registry["nodes"])

    identity = next(item for item in registry["task_families"] if item["slug"] == "identity_access")
    assert identity["readiness"] == "ready"
    assert identity["matching_mcp_servers"][0]["id"] == mcp.id
    assert any(skill["slug"] == "keycloak-safety" for skill in identity["matching_skills"])
    assert identity["capability_packs"][0]["slug"] == "identity-keycloak"
    assert "keycloak_apply_access_change" in identity["capability_packs"][0]["tool_names"]
    assert identity["preferred_nodes"] == [
        "trigger/manual",
        "agent/mcp_call",
        "logic/human_approval",
        "agent/mcp_call",
        "output/report",
    ]


def test_capability_registry_maps_incident_response_to_observability_pack():
    user = User.objects.create_user(username="cap-incident", password="x", is_staff=True)
    mcp = MCPServerPool.objects.create(
        owner=user,
        name="Observability MCP",
        description="Grafana Prometheus Loki PagerDuty Jira alert and incident automation",
        transport=MCPServerPool.TRANSPORT_SSE,
        url="http://127.0.0.1:8770/mcp",
    )

    registry = build_studio_capability_registry(user, server_count=0)

    incident = next(item for item in registry["task_families"] if item["slug"] == "incident_response")
    assert incident["readiness"] == "partial"
    assert incident["missing"] == ["skill"]
    assert incident["matching_mcp_servers"][0]["id"] == mcp.id
    assert incident["capability_packs"][0]["slug"] == "observability-incident"
    assert "incident_create_or_update_ticket" in incident["capability_packs"][0]["tool_names"]
    assert incident["preferred_nodes"] == [
        "trigger/monitoring",
        "agent/mcp_call",
        "agent/llm_query",
        "logic/human_approval",
        "agent/mcp_call",
        "output/report",
    ]


def test_capabilities_endpoint_returns_pilot_registry():
    user = User.objects.create_user(username="cap-endpoint", password="x", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/capabilities/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy"]["service_specific_work"] == "mcp_plus_skills"
    assert any(item["slug"] == "identity_access" for item in payload["task_families"])
    assert any(item["type"] == "ops/service_action" for item in payload["nodes"])
    log_query = next(item for item in payload["nodes"] if item["type"] == "ops/log_query")
    assert "docker" in log_query["input_schema"]["properties"]["source"]["enum"]
    assert "logs" in log_query["output_schema"]["properties"]
    assert any(pack["slug"] == "kubernetes-operations" for pack in payload["capability_packs"])
    assert any(pack["slug"] == "observability-incident" for pack in payload["capability_packs"])
    keycloak_pack = next(pack for pack in payload["capability_packs"] if pack["slug"] == "identity-keycloak")
    apply_tool = next(tool for tool in keycloak_pack["tools"] if tool["tool_name"] == "keycloak_apply_access_change")
    assert apply_tool["requires_approval"] is True
    assert apply_tool["input_schema"]["properties"]["operation"]["enum"] == ["add", "remove"]
    incident_pack = next(pack for pack in payload["capability_packs"] if pack["slug"] == "observability-incident")
    ticket_tool = next(tool for tool in incident_pack["tools"] if tool["tool_name"] == "incident_create_or_update_ticket")
    assert ticket_tool["requires_approval"] is True
    assert ticket_tool["input_schema"]["properties"]["severity"]["enum"] == ["critical", "warning", "info", "unknown"]


def test_node_manifests_endpoint_returns_schema_contract():
    user = User.objects.create_user(username="node-manifest-endpoint", password="x", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/node-manifests/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == 1
    assert payload["count"] == len(payload["nodes"])
    assert payload["count"] >= 30
    mcp_call = next(item for item in payload["nodes"] if item["type"] == "agent/mcp_call")
    assert "arguments" in mcp_call["input_schema"]["properties"]
    assert mcp_call["input_schema"]["properties"]["permission_mode"]["enum"] == ["SAFE", "ASK", "AUTO"]
    service_action = next(item for item in payload["nodes"] if item["type"] == "ops/service_action")
    assert service_action["requires_approval_by_default"] is True
    assert service_action["input_schema"]["properties"]["action"]["enum"] == ["start", "stop", "restart", "reload"]
    file_action = next(item for item in payload["nodes"] if item["type"] == "ops/file_action")
    assert file_action["input_schema"]["properties"]["action"]["enum"] == ["read", "write"]
    assert "file" in file_action["output_schema"]["properties"]
    package_action = next(item for item in payload["nodes"] if item["type"] == "ops/package_action")
    assert package_action["input_schema"]["properties"]["action"]["enum"] == ["list_updates", "install", "update", "remove"]
    assert "package_action" in package_action["output_schema"]["properties"]
    disk_cleanup = next(item for item in payload["nodes"] if item["type"] == "ops/disk_cleanup")
    assert disk_cleanup["input_schema"]["properties"]["action"]["enum"] == ["inspect", "journal_vacuum", "tmp_cleanup"]
    assert "disk_cleanup" in disk_cleanup["output_schema"]["properties"]
    backup_check = next(item for item in payload["nodes"] if item["type"] == "ops/backup_restore_check")
    assert backup_check["input_schema"]["properties"]["action"]["enum"] == ["inspect", "verify_latest"]
    assert "backup_restore_check" in backup_check["output_schema"]["properties"]


def test_pipeline_assistant_context_includes_capability_registry(monkeypatch):
    user = User.objects.create_user(username="cap-assistant", password="x", is_staff=True)
    captured = {}

    def fake_build_pipeline_assistant_response(**kwargs):
        captured["assistant_context"] = kwargs["assistant_context"]
        return {
            "reply": "draft",
            "requirements": [],
            "assumptions": [],
            "questions": [],
            "resource_plan": {"servers": [], "agents": [], "mcp_servers": [], "skills": [], "missing": [], "notes": []},
            "target_node_id": None,
            "node_patch": {},
            "graph_patch": {
                "anchor_node_id": None,
                "nodes": [],
                "edges": [],
                "update_nodes": [],
                "remove_node_ids": [],
                "remove_edge_ids": [],
            },
            "node_explanations": {},
            "confidence": 1.0,
            "warnings": [],
            "patch_summary": "",
            "suggested_next_actions": [],
        }

    monkeypatch.setattr(
        "studio.views.pipeline_assistant_views.build_pipeline_assistant_response",
        fake_build_pipeline_assistant_response,
    )

    client = Client()
    client.force_login(user)
    response = client.post(
        "/api/studio/pipelines/assistant/",
        data=_json({"user_message": "Create Keycloak workflow", "nodes": [], "edges": [], "history": []}),
        content_type="application/json",
    )

    assert response.status_code == 200
    registry = captured["assistant_context"]["capability_registry"]
    assert registry["strategy"]["default_execution_node"] == "agent/mcp_call"
    assert any(item["slug"] == "identity_access" for item in registry["task_families"])
    assert any(pack["slug"] == "gitlab-ci-support" for pack in registry["capability_packs"])
    assert any(pack["slug"] == "observability-incident" for pack in registry["capability_packs"])
    recommendations = captured["assistant_context"]["template_recommendations"]
    assert recommendations[0]["slug"] == "pilot-keycloak-access-change"
    assert "logic/human_approval" in recommendations[0]["node_types"]
