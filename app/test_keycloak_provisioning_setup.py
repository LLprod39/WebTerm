import json

import pytest
from django.contrib.auth.models import User

from studio.keycloak_provisioning import (
    KEYCLOAK_MCP_URL,
    KEYCLOAK_OPS_PIPELINE_SPECS,
    KEYCLOAK_PIPELINE_NAME,
    ensure_keycloak_mcp_server,
    ensure_keycloak_ops_pipelines,
    ensure_keycloak_pipeline,
)
from studio.models import PipelineTrigger


@pytest.mark.django_db
def test_ensure_keycloak_mcp_server_creates_http_server_entry():
    user = User.objects.create_user(username="kc-owner", password="x")

    server = ensure_keycloak_mcp_server(user)

    assert server.owner == user
    assert server.name == "Keycloak Admin"
    assert server.transport == "sse"
    assert server.url == KEYCLOAK_MCP_URL


@pytest.mark.django_db
def test_ensure_keycloak_pipeline_wires_manual_webhook_and_agent_mcp_server():
    user = User.objects.create_user(username="kc-pipeline", password="x")
    server = ensure_keycloak_mcp_server(user)

    pipeline = ensure_keycloak_pipeline(user, server)

    assert pipeline.name == KEYCLOAK_PIPELINE_NAME
    nodes = {node["id"]: node for node in pipeline.nodes}
    assert nodes["start_manual"]["type"] == "trigger/manual"
    assert nodes["start_webhook"]["type"] == "trigger/webhook"
    assert nodes["environment_preflight"]["data"]["mcp_server_id"] == server.id
    assert nodes["existing_user_lookup"]["data"]["tool_name"] == "keycloak_find_user"
    assert nodes["execute_keycloak_plan"]["type"] == "agent/react"
    assert nodes["execute_keycloak_plan"]["data"]["mcp_server_ids"] == [server.id]

    triggers = {trigger.node_id: trigger for trigger in pipeline.triggers.all()}
    assert set(triggers) == {"start_manual", "start_webhook"}
    assert triggers["start_webhook"].trigger_type == PipelineTrigger.TYPE_WEBHOOK
    assert triggers["start_webhook"].webhook_payload_map["client_roles"] == "client_roles"


@pytest.mark.django_db
def test_ensure_keycloak_ops_pipelines_create_fixed_test_and_prod_with_manual_approval():
    user = User.objects.create_user(username="kc-ops", password="x")
    server = ensure_keycloak_mcp_server(user)

    pipelines = ensure_keycloak_ops_pipelines(user, server)

    assert set(pipelines) == {"test", "prod"}

    for profile_name, spec in KEYCLOAK_OPS_PIPELINE_SPECS.items():
        pipeline = pipelines[profile_name]
        assert pipeline.name == spec["name"]
        nodes = {node["id"]: node for node in pipeline.nodes}
        node_types = {node["type"] for node in pipeline.nodes}

        assert nodes["start_manual"]["type"] == "trigger/manual"
        assert nodes["start_webhook"]["type"] == "trigger/webhook"
        assert nodes["environment_preflight"]["data"]["mcp_server_id"] == server.id
        assert json.loads(nodes["environment_preflight"]["data"]["arguments_text"]) == {"profile": profile_name}
        assert nodes["execute_identity_actions"]["type"] == "agent/react"
        assert nodes["execute_identity_actions"]["data"]["mcp_server_ids"] == [server.id]
        assert profile_name in nodes["execute_identity_actions"]["data"]["goal"]
        assert nodes["execute_platform_actions"]["type"] == "agent/react"
        assert nodes["execute_platform_actions"]["data"]["mcp_server_ids"] == [server.id]
        assert profile_name in nodes["execute_platform_actions"]["data"]["goal"]
        assert nodes["await_execution_approval"]["type"] == "logic/human_approval"
        assert nodes["await_execution_approval"]["data"]["manual_link_only"] is True
        assert "output/email" not in node_types
        assert "output/telegram" not in node_types

        triggers = {trigger.node_id: trigger for trigger in pipeline.triggers.all()}
        assert set(triggers) == {"start_manual", "start_webhook"}
        assert triggers["start_webhook"].trigger_type == PipelineTrigger.TYPE_WEBHOOK
        assert triggers["start_webhook"].webhook_payload_map["task"] == "task"
