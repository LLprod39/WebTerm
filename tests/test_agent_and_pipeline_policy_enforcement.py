from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.tools.registry import ToolRegistry
from app.sudo_policy import (
    command_prefers_controlled_sudo,
    output_indicates_privilege_error,
    wrap_command_for_controlled_sudo,
)
from servers.agents.agent_engine import AgentEngine
from servers.agents.agent_sessions import AgentSessionManager
from servers.agents.multi_agent_engine import MultiAgentEngine
from servers.models import ServerAgent
from studio.skill_registry import SkillDefinition


def _invalid_skill_definition() -> SkillDefinition:
    return SkillDefinition(
        slug="invalid-skill",
        name="Invalid Skill",
        description="invalid runtime policy test",
        path="/tmp/invalid/SKILL.md",
        tags=(),
        service="keycloak",
        category="",
        safety_level="",
        ui_hint="",
        guardrail_summary=(),
        recommended_tools=(),
        runtime_policy={"applicable_tool_patterns": "^keycloak_"},
        metadata={},
        content="# invalid",
    )


def test_agent_engine_reprompts_when_first_response_has_tool_intent_without_action():
    engine = AgentEngine.__new__(AgentEngine)
    engine.enabled_tools = ["ssh_execute", "read_console"]
    engine.mcp_tools = {}

    assert engine._should_reprompt_missing_action(
        "THOUGHT: Сначала проверю journalctl за последний час, затем вызову инструмент.",
        [],
    )


def test_agent_engine_accepts_explicit_final_without_action():
    engine = AgentEngine.__new__(AgentEngine)
    engine.enabled_tools = ["ssh_execute"]
    engine.mcp_tools = {}

    assert not engine._should_reprompt_missing_action(
        "THOUGHT: Задача завершена. Итог: ошибок не найдено.",
        [],
    )


def test_agent_engine_accepts_final_after_tool_call():
    engine = AgentEngine.__new__(AgentEngine)
    engine.enabled_tools = ["ssh_execute"]
    engine.mcp_tools = {}

    # Явно финальный ответ после вызова инструмента — не репромптим.
    assert not engine._should_reprompt_missing_action(
        "THOUGHT: Итог: сервис стабилен, ошибок в журнале нет.",
        [{"tool": "ssh_execute"}],
    )


def test_agent_engine_reprompts_intent_text_early_but_not_after_many_tool_calls():
    engine = AgentEngine.__new__(AgentEngine)
    engine.enabled_tools = ["ssh_execute"]
    engine.mcp_tools = {}

    intent_text = "THOUGHT: Проверю итоговое состояние в отчёте."
    # Ранний этап (<=2 вызова инструментов): интент без ACTION — репромптим.
    assert engine._should_reprompt_missing_action(intent_text, [{"tool": "ssh_execute"}])
    # После 3+ вызовов инструментов доверяем модели завершить ход.
    assert not engine._should_reprompt_missing_action(
        intent_text,
        [{"tool": "ssh_execute"}, {"tool": "ssh_execute"}, {"tool": "ssh_execute"}],
    )


def test_agent_engine_validates_required_tool_arguments_before_execution():
    spec = ToolSpec(
        name="analyze_output",
        category="general",
        risk="read",
        description="Analyze output",
        input_schema={
            "text": {"type": "string", "required": True},
            "question": {"type": "string", "required": True},
        },
    )

    error = AgentEngine._validate_tool_args("analyze_output", {}, spec)

    assert "missing required parameter" in error
    assert "text" in error
    assert "question" in error
    assert 'ACTION: analyze_output {"text": "<text>", "question": "<question>"}' in error


def test_sudo_policy_detects_privileged_reads_and_permission_errors():
    assert command_prefers_controlled_sudo("docker ps 2>/dev/null | head")
    assert command_prefers_controlled_sudo("journalctl -u nginx -n 100")
    assert not command_prefers_controlled_sudo("docker restart nginx")
    assert output_indicates_privilege_error(
        "permission denied while trying to connect to the Docker daemon socket",
        "",
    )
    assert wrap_command_for_controlled_sudo("docker ps | head") == "sudo bash -lc 'docker ps | head'"


def test_agent_session_auto_sudo_for_privileged_read(monkeypatch):
    server = SimpleNamespace(id=1, name="prod", sudo_auth_mode="nopasswd")
    manager = AgentSessionManager([server], sudo_policy="approved")
    manager.connections[1] = SimpleNamespace(proc=object(), conn=object(), server_id=1, server_name="prod")
    captured = {}

    async def fake_execute_controlled_sudo(session, server_obj, command, *, reason, original_result=None):
        captured.update({"server": server_obj.name, "command": command, "reason": reason, "original": original_result})
        return {"stdout": "ok", "stderr": "", "exit_code": 0, "duration_ms": 1}

    monkeypatch.setattr(manager, "_execute_controlled_sudo", fake_execute_controlled_sudo)

    result = async_to_sync(manager.execute)(1, "docker ps 2>/dev/null | head")

    assert result["exit_code"] == 0
    assert captured == {
        "server": "prod",
        "command": "docker ps 2>/dev/null | head",
        "reason": "auto_sudo_privileged_read",
        "original": None,
    }


def test_agent_session_retries_with_sudo_after_permission_error(monkeypatch):
    server = SimpleNamespace(id=1, name="prod", sudo_auth_mode="stored_password")
    manager = AgentSessionManager([server], sudo_policy="approved")
    manager.connections[1] = SimpleNamespace(proc=object(), conn=object(), server_id=1, server_name="prod")
    captured = {}
    original = {
        "stdout": "Failed to connect: permission denied",
        "stderr": "",
        "exit_code": 1,
        "duration_ms": 1,
    }

    async def fake_execute_via_pty(session, command):
        return original

    async def fake_execute_controlled_sudo(session, server_obj, command, *, reason, original_result=None):
        captured.update({"command": command, "reason": reason, "original": original_result})
        return {"stdout": "ok", "stderr": "", "exit_code": 0, "duration_ms": 1}

    monkeypatch.setattr(manager, "_execute_via_pty", fake_execute_via_pty)
    monkeypatch.setattr(manager, "_execute_controlled_sudo", fake_execute_controlled_sudo)

    result = async_to_sync(manager.execute)(1, "systemctl status nginx")

    assert result["exit_code"] == 0
    assert captured["command"] == "systemctl status nginx"
    assert captured["reason"] == "auto_sudo_after_permission_denied"
    assert captured["original"] == original


@pytest.mark.django_db(transaction=True)
def test_agent_engine_fails_fast_on_invalid_skill_policy():
    user = User.objects.create_user(username="agent-policy-user", password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Policy Agent",
        mode=ServerAgent.MODE_FULL,
        agent_type=ServerAgent.TYPE_CUSTOM,
        commands=[],
        max_iterations=3,
    )

    engine = AgentEngine(agent=agent, servers=[], user=user, skills=[_invalid_skill_definition()])
    run = async_to_sync(engine.run)()

    assert run.status == run.STATUS_FAILED
    assert "Invalid skill policy configuration" in run.ai_analysis


@pytest.mark.django_db(transaction=True)
def test_multi_agent_engine_fails_fast_on_invalid_skill_policy():
    user = User.objects.create_user(username="multi-policy-user", password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Multi Policy Agent",
        mode=ServerAgent.MODE_MULTI,
        agent_type=ServerAgent.TYPE_MULTI_HEALTH,
        commands=[],
        max_iterations=3,
    )

    engine = MultiAgentEngine(agent=agent, servers=[], user=user, skills=[_invalid_skill_definition()])
    run = async_to_sync(engine.run)(plan_only=True)

    assert run.status == run.STATUS_FAILED
    assert "Invalid skill policy configuration" in run.ai_analysis


@pytest.mark.django_db(transaction=True)
def test_multi_agent_task_requires_verification_before_final_answer(monkeypatch):
    user = User.objects.create_user(username="multi-subagent-user", password="x")
    agent = ServerAgent.objects.create(
        user=user,
        name="Deploy Multi Agent",
        mode=ServerAgent.MODE_MULTI,
        agent_type=ServerAgent.TYPE_DEPLOY_WATCHER,
        commands=[],
        max_iterations=6,
    )
    engine = MultiAgentEngine(agent=agent, servers=[], user=user)
    engine.session = SimpleNamespace(get_connected_info=lambda: [])
    engine.server_memory_prompt = "Сервер: prod-web-1"
    engine.enabled_tools = ["ssh_execute"]
    engine.tool_registry = ToolRegistry(
        {
            "ssh_execute": ToolSpec(
                name="ssh_execute",
                category="ssh",
                risk="exec",
                description="Execute command",
                input_schema={},
                requires_verification=True,
            ),
        }
    )

    responses = iter(
        [
            'THOUGHT: Сначала проверю сервис\nACTION: ssh_execute {"server":"prod-web-1","command":"systemctl status nginx"}',
            'THOUGHT: Перезапускаю сервис\nACTION: ssh_execute {"server":"prod-web-1","command":"systemctl restart nginx"}',
            "THOUGHT: Готово, задача завершена",
            "THOUGHT: Уже всё сделал",
            "THOUGHT: Больше шагов нет",
            "THOUGHT: Финал",
        ]
    )

    async def fake_call_llm_history(_history):
        return next(responses)

    async def fake_execute_tool(name, args, **kwargs):
        spec = kwargs["tool_registry"].get(name)
        decision = kwargs["permission_engine"].evaluate(spec, args)
        if not decision.allowed:
            return decision.reason
        kwargs["permission_engine"].record_success(spec, args, "ok")
        return "ok"

    monkeypatch.setattr(engine, "_call_llm_history", fake_call_llm_history)
    monkeypatch.setattr(engine, "_execute_tool", fake_execute_tool)

    task = {
        "id": 1,
        "name": "Перезапустить nginx и подтвердить результат",
        "description": "Сделай controlled restart nginx на prod-web-1 и проверь итоговое состояние",
        "role": "deploy_operator",
        "tool_names": ["ssh_execute"],
        "max_iterations": 6,
    }

    with pytest.raises(RuntimeError, match="непроверенные|verification"):
        async_to_sync(engine._run_task)(task, "", 10**9)
