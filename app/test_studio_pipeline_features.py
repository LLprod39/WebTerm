from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from servers.agent_tools import tool_list_skills, tool_read_skill
from studio.mcp_tool_runtime import (
    MCPBoundTool,
    build_mcp_tools_description,
    execute_bound_mcp_tool,
    load_mcp_tool_bindings,
)
from studio.models import AgentConfig, Pipeline, PipelineTrigger
from studio.pipeline_executor import _coerce_mcp_arguments
from studio.skill_policy import apply_skill_policies, compile_skill_policies
from studio.skill_registry import get_skill, list_skills, normalise_skill_slugs, resolve_skills
from studio.views._views_all import _normalise_related_ids


@pytest.mark.django_db
def test_pipeline_sync_triggers_from_nodes_creates_updates_and_removes_triggers():
    user = User.objects.create_user(username="pipeline-user", password="x")
    pipeline = Pipeline.objects.create(
        name="Trigger Sync",
        owner=user,
        nodes=[
            {
                "id": "node_webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": "Webhook Start",
                    "is_active": True,
                    "webhook_payload_map": {"branch": "ref"},
                },
            },
            {
                "id": "node_schedule",
                "type": "trigger/schedule",
                "position": {"x": 100, "y": 0},
                "data": {
                    "label": "Nightly",
                    "is_active": False,
                    "cron_expression": "0 4 * * *",
                },
            },
        ],
        edges=[],
    )

    pipeline.sync_triggers_from_nodes()

    triggers = {trigger.node_id: trigger for trigger in pipeline.triggers.all()}
    assert set(triggers) == {"node_webhook", "node_schedule"}
    assert triggers["node_webhook"].trigger_type == PipelineTrigger.TYPE_WEBHOOK
    assert triggers["node_webhook"].webhook_payload_map == {"branch": "ref"}
    assert triggers["node_schedule"].cron_expression == "0 4 * * *"
    assert triggers["node_schedule"].is_active is False

    pipeline.nodes = [
        {
            "id": "node_schedule",
            "type": "trigger/schedule",
            "position": {"x": 100, "y": 0},
            "data": {
                "label": "Hourly",
                "is_active": True,
                "cron_expression": "0 * * * *",
            },
        }
    ]
    pipeline.save(update_fields=["nodes"])
    pipeline.sync_triggers_from_nodes()

    schedule_trigger = pipeline.triggers.get(node_id="node_schedule")
    assert pipeline.triggers.count() == 1
    assert schedule_trigger.name == "Hourly"
    assert schedule_trigger.cron_expression == "0 * * * *"
    assert schedule_trigger.is_active is True


def test_coerce_mcp_arguments_prefers_arguments_text_over_stale_arguments_dict():
    arguments, error = _coerce_mcp_arguments(
        {
            "arguments": {"stale": True},
            "arguments_text": '{"path": "{repo_path}"}',
        }
    )

    assert error is None
    assert arguments == {"path": "{repo_path}"}


def test_coerce_mcp_arguments_requires_json_object():
    arguments, error = _coerce_mcp_arguments({"arguments_text": "[]"})

    assert arguments is None
    assert error == "MCP arguments must be a JSON object"


def test_normalise_related_ids_accepts_ints_and_object_payloads():
    assert _normalise_related_ids([1, "2", {"id": 3}, {"id": "4"}, None, {"id": "bad"}]) == [1, 2, 3, 4]


def test_normalise_skill_slugs_accepts_strings_and_object_payloads():
    assert normalise_skill_slugs(
        ["keycloak-safety", {"slug": "keycloak-prod-profile"}, {"name": "Keycloak TEST Profile"}, "", None]
    ) == ["keycloak-safety", "keycloak-prod-profile", "Keycloak TEST Profile"]


def test_skill_registry_lists_repo_skills_and_resolves_missing_entries():
    skills = list_skills()
    skill_slugs = {skill.slug for skill in skills}

    assert {"keycloak-safety", "keycloak-test-profile", "keycloak-prod-profile"} <= skill_slugs

    resolved, errors = resolve_skills(["keycloak-safety", "missing-skill"])

    assert [skill.slug for skill in resolved] == ["keycloak-safety"]
    assert errors == ["missing-skill: not found"]
    prod_skill = next(skill for skill in resolved + skills if skill.slug == "keycloak-prod-profile")
    assert prod_skill.runtime_policy["pinned_arguments"]["profile"] == "prod"


def test_get_skill_returns_markdown_body_without_frontmatter():
    skill = get_skill("keycloak-safety")

    assert skill.content.startswith("# Keycloak Safety Workflow")
    assert not skill.content.startswith("---")


@pytest.mark.django_db
def test_agent_config_to_dict_includes_skill_metadata_and_errors():
    user = User.objects.create_user(username="skills-user", password="x")
    agent = AgentConfig.objects.create(
        name="Skill Agent",
        owner=user,
        skill_slugs=["keycloak-safety", "missing-skill"],
    )

    payload = agent.to_dict()

    assert payload["skill_slugs"] == ["keycloak-safety", "missing-skill"]
    assert [skill["slug"] for skill in payload["skills"]] == ["keycloak-safety"]
    assert payload["skill_errors"] == ["missing-skill: not found"]


@pytest.mark.asyncio
async def test_load_mcp_tool_bindings_builds_safe_aliases_and_collects_errors(monkeypatch):
    good_server = SimpleNamespace(id=1, name="Keycloak Admin")
    bad_server = SimpleNamespace(id=2, name="Broken MCP")

    async def fake_list_mcp_tools(server):
        if server.id == 2:
            raise RuntimeError("offline")
        return [
            {
                "name": "create_user",
                "description": "Create a Keycloak user",
                "inputSchema": {
                    "type": "object",
                    "properties": {"username": {"type": "string", "description": "Login name"}},
                    "required": ["username"],
                },
            },
            {"name": "assign-client-roles", "description": "Assign client roles"},
        ]

    monkeypatch.setattr("studio.mcp_tool_runtime.list_mcp_tools", fake_list_mcp_tools)

    bindings, errors = await load_mcp_tool_bindings([good_server, bad_server])  # type: ignore[arg-type]

    assert set(bindings) == {"mcp_keycloak_admin_create_user", "mcp_keycloak_admin_assign_client_roles"}
    assert errors == ["Broken MCP: offline"]
    description = build_mcp_tools_description(bindings)
    assert "Original MCP tool: create_user" in description
    assert "username: string (required)" in description


@pytest.mark.asyncio
async def test_execute_bound_mcp_tool_returns_error_text(monkeypatch):
    async def fake_call_mcp_tool(server, tool_name, arguments):
        assert server.name == "Keycloak Admin"
        assert tool_name == "create_user"
        assert arguments == {"username": "alice"}
        return {"isError": True, "content": [{"type": "text", "text": "User already exists"}]}

    monkeypatch.setattr("studio.mcp_tool_runtime.call_mcp_tool", fake_call_mcp_tool)

    bindings = {
        "mcp_keycloak_admin_create_user": MCPBoundTool(
            action_name="mcp_keycloak_admin_create_user",
            server=SimpleNamespace(id=1, name="Keycloak Admin"),  # type: ignore[arg-type]
            tool_name="create_user",
            description="Create a Keycloak user",
            input_schema={"type": "object"},
        )
    }

    result = await execute_bound_mcp_tool(bindings, "mcp_keycloak_admin_create_user", {"username": "alice"})

    assert "User already exists" in result


@pytest.mark.asyncio
async def test_skill_tools_list_and_read_attached_skill():
    class DummySession:
        def list_skills(self):
            return [
                {
                    "slug": "keycloak-safety",
                    "name": "Keycloak Safety Workflow",
                    "description": "Safe Keycloak workflow",
                    "tags": ["keycloak", "iam"],
                    "path": "/tmp/keycloak-safety/SKILL.md",
                }
            ]

        def get_skill(self, skill_ref):
            if skill_ref not in {"keycloak-safety", "Keycloak Safety Workflow"}:
                return None
            return {
                "slug": "keycloak-safety",
                "name": "Keycloak Safety Workflow",
                "description": "Safe Keycloak workflow",
                "tags": ["keycloak", "iam"],
                "path": "/tmp/keycloak-safety/SKILL.md",
                "content": "# Keycloak Safety Workflow\n\nAlways run preflight first.",
            }

    list_result = await tool_list_skills(DummySession())  # type: ignore[arg-type]
    read_result = await tool_read_skill(DummySession(), skill="keycloak-safety")  # type: ignore[arg-type]

    assert '"slug": "keycloak-safety"' in list_result.result
    assert "# Keycloak Safety Workflow" in read_result.result


def test_skill_policy_compilation_and_enforcement_for_keycloak():
    skills, errors = resolve_skills(["keycloak-safety", "keycloak-prod-profile"])
    assert errors == []

    policies, policy_errors = compile_skill_policies(skills)
    assert policy_errors == []
    assert len(policies) == 2

    binding = MCPBoundTool(
        action_name="mcp_keycloak_admin_keycloak_create_user",
        server=SimpleNamespace(id=1, name="Keycloak Admin"),  # type: ignore[arg-type]
        tool_name="keycloak_create_user",
        description="Create user",
        input_schema={"type": "object"},
    )

    args, messages, error = apply_skill_policies(policies, binding, {"username": "alice"}, set())
    assert error == "Blocked by skill 'Keycloak Safety Workflow': run the required preflight MCP tools first: keycloak_current_environment."
    assert messages == []

    args, messages, error = apply_skill_policies(
        policies,
        binding,
        {"username": "alice"},
        {"keycloak_current_environment"},
    )
    assert error is None
    assert args["profile"] == "prod"
    assert any("profile='prod'" in message for message in messages)


def test_skill_policy_blocks_profile_switch_tool():
    skills, errors = resolve_skills(["keycloak-safety", "keycloak-test-profile"])
    assert errors == []

    policies, policy_errors = compile_skill_policies(skills)
    assert policy_errors == []

    binding = MCPBoundTool(
        action_name="mcp_keycloak_admin_keycloak_use_profile",
        server=SimpleNamespace(id=1, name="Keycloak Admin"),  # type: ignore[arg-type]
        tool_name="keycloak_use_profile",
        description="Switch profile",
        input_schema={"type": "object"},
    )

    _args, _messages, error = apply_skill_policies(
        policies,
        binding,
        {"profile": "prod"},
        {"keycloak_current_environment"},
    )
    assert error == "Blocked by skill 'Keycloak Safety Workflow': MCP tool 'keycloak_use_profile' is forbidden by corporate guardrails."
