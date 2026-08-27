"""Focused tests for complex-task agent budgets, Fast routing, Nova partial stop, Multi handoff."""

from __future__ import annotations

import inspect

import pytest

from servers.agents.agent_budgets import (
    FAST_PLANNER_COMMAND_CAP,
    FAST_PLANNER_COMMAND_HARD_MAX,
    FULL_DEFAULT_COMMAND_TIMEOUT_SEC,
    FULL_DEFAULT_MAX_ITERATIONS,
    FULL_DEFAULT_SESSION_TIMEOUT_SEC,
    MULTI_DEFAULT_COMMAND_TIMEOUT_SEC,
    MULTI_DEFAULT_SESSION_TIMEOUT_SEC,
    MULTI_MAX_TASK_ITERATIONS,
    clamp_command_timeout,
    clamp_full_iterations,
)
from servers.agents.agent_pilot_policy import (
    PILOT_MAX_ITERATIONS,
    PILOT_MAX_SESSION_TIMEOUT_SECONDS,
)
from servers.services.agent_complexity import (
    classify_goal_complexity,
    ensure_verification_task,
    plan_mentions_mutation,
    resolve_fast_complex_action,
)
from servers.services.task_handoff import (
    append_structured_task_context,
    build_task_handoff,
    extract_handoff_facts,
)
from servers.services.terminal_ai.agent.prompts import (
    build_partial_stop_summary,
    compact_agent_history,
)
from servers.services.terminal_ai.plan_items import apply_fast_complexity_routing
from servers.services.terminal_ai.prompts import build_planner_prompt_parts


def test_shipped_budget_defaults_meet_complex_task_bar():
    assert FULL_DEFAULT_MAX_ITERATIONS > 20
    assert FULL_DEFAULT_SESSION_TIMEOUT_SEC > 600
    assert MULTI_MAX_TASK_ITERATIONS > 7
    assert MULTI_DEFAULT_SESSION_TIMEOUT_SEC > 900
    assert FULL_DEFAULT_COMMAND_TIMEOUT_SEC >= 90
    assert MULTI_DEFAULT_COMMAND_TIMEOUT_SEC >= 90
    assert FAST_PLANNER_COMMAND_CAP > 6
    assert FAST_PLANNER_COMMAND_HARD_MAX >= FAST_PLANNER_COMMAND_CAP
    assert clamp_command_timeout(30) == 30
    assert clamp_command_timeout(9999) == 300
    assert clamp_full_iterations(5) == 5
    assert clamp_full_iterations(500) == 100


def test_create_paths_use_runtime_budget_policy_without_legacy_hardcodes():
    """Create API + assistant action must not hardcode 20/600 when payload omits budgets."""
    import inspect

    from servers import assistant_actions
    from servers.views import server_agents

    create_src = inspect.getsource(server_agents.agent_create)
    assistant_src = inspect.getsource(assistant_actions.create_agent)
    assert "resolve_agent_runtime_budget" in create_src
    assert "PILOT_MAX_ITERATIONS" in create_src
    assert "PILOT_MAX_SESSION_TIMEOUT_SECONDS" in create_src
    assert 'max_iterations", 20)' not in create_src
    assert 'session_timeout_seconds", 600)' not in create_src
    assert "FULL_DEFAULT_MAX_ITERATIONS" in assistant_src
    assert "FULL_DEFAULT_SESSION_TIMEOUT_SEC" in assistant_src
    # Explicit legacy hardcodes must be gone
    assert 'max_iterations") or 20' not in assistant_src
    assert 'session_timeout_seconds") or 600' not in assistant_src


@pytest.mark.django_db
def test_agent_create_api_omitted_budgets_use_pilot_safe_defaults():
    """A non-operator cannot inherit legacy budgets above the pilot caps."""
    import json

    from django.contrib.auth.models import User
    from django.test import Client

    from core_ui.models import UserAppPermission
    from servers.models import Server, ServerAgent

    user = User.objects.create_user(username="budget-create-user", password="x")
    UserAppPermission.objects.update_or_create(user=user, feature="agents", defaults={"allowed": True})
    server = Server.objects.create(
        user=user,
        name="budget-srv",
        host="10.0.0.55",
        username="root",
        auth_method="password",
        server_type="ssh",
    )
    client = Client()
    client.force_login(user)
    response = client.post(
        "/servers/api/agents/create/",
        data=json.dumps(
            {
                "mode": "full",
                "agent_type": "custom",
                "name": "Complex Default Agent",
                "goal": "Investigate nginx 502 and verify",
                "server_ids": [server.id],
                # intentionally omit max_iterations and session_timeout_seconds
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body.get("success") is True
    agent = ServerAgent.objects.get(id=body["id"])
    assert agent.max_iterations == PILOT_MAX_ITERATIONS
    assert agent.session_timeout_seconds == PILOT_MAX_SESSION_TIMEOUT_SECONDS


def test_create_agent_dialog_seeds_pilot_safe_defaults():
    from pathlib import Path

    src = Path("frontend/src/pages/agents-page/useCreateAgentDialogState.ts").read_text(encoding="utf-8")
    assert f"useState({PILOT_MAX_ITERATIONS})" in src
    assert f"useState({PILOT_MAX_SESSION_TIMEOUT_SECONDS})" in src
    assert "max_iterations || 40" in src or "max_iterations || 40)" in src
    assert "session_timeout_seconds || 1200" in src


def test_model_and_engine_defaults_wire_to_budgets():
    from servers.agents.agent_engine import DEFAULT_COMMAND_TIMEOUT, MAX_ITERATIONS_CAP, SESSION_TIMEOUT_DEFAULT
    from servers.agents.multi_agent_engine_config import (
        DEFAULT_COMMAND_TIMEOUT as MULTI_CMD,
    )
    from servers.agents.multi_agent_engine_config import (
        MAX_TASK_ITERATIONS,
    )
    from servers.agents.multi_agent_engine_config import (
        SESSION_TIMEOUT_DEFAULT as MULTI_SESSION,
    )
    from servers.models_agents import ServerAgent

    field_iters = ServerAgent._meta.get_field("max_iterations")
    field_timeout = ServerAgent._meta.get_field("session_timeout_seconds")
    assert field_iters.default == FULL_DEFAULT_MAX_ITERATIONS
    assert field_timeout.default == FULL_DEFAULT_SESSION_TIMEOUT_SEC
    assert SESSION_TIMEOUT_DEFAULT == FULL_DEFAULT_SESSION_TIMEOUT_SEC
    assert DEFAULT_COMMAND_TIMEOUT >= 90
    assert MAX_ITERATIONS_CAP >= FULL_DEFAULT_MAX_ITERATIONS
    assert MAX_TASK_ITERATIONS == MULTI_MAX_TASK_ITERATIONS
    assert MULTI_SESSION == MULTI_DEFAULT_SESSION_TIMEOUT_SEC
    assert MULTI_CMD >= 90


def test_agent_engine_runner_uses_command_timeout_from_engine():
    src = inspect.getsource(
        __import__("servers.agents.agent_engine_runner", fromlist=["run_agent_engine"]).run_agent_engine
    )
    assert 'command_timeout=int(getattr(engine, "command_timeout"' in src or "command_timeout=" in src
    assert "command_timeout=30" not in src


def test_complexity_simple_vs_complex_russian_english():
    simple = classify_goal_complexity("df -h")
    assert simple.level in ("simple", "medium")
    assert not simple.is_complex

    simple2 = classify_goal_complexity("что такое nginx")
    assert simple2.is_simple

    complex_ru = classify_goal_complexity(
        "nginx 502, найди root cause, почини upstream и проверь health после изменений"
    )
    assert complex_ru.is_complex
    assert complex_ru.score >= 6

    complex_en = classify_goal_complexity(
        "Production incident: migrate database, deploy rollback plan, verify smoke tests on multi-server cluster"
    )
    assert complex_en.is_complex


def test_fast_complex_routing_ask_and_upgrade_not_silent_execute():
    assessment = classify_goal_complexity("Разберись с инцидентом nginx, почини и проверь после")
    ask = resolve_fast_complex_action(assessment, requested_mode="fast", policy="ask")
    assert ask["action"] == "ask"
    assert "Nova" in ask["assistant_text"] or "nova" in ask["assistant_text"].lower()

    upgrade = resolve_fast_complex_action(assessment, requested_mode="fast", policy="upgrade")
    assert upgrade["action"] == "upgrade"
    assert upgrade["execution_mode"] == "agent"

    allow = resolve_fast_complex_action(assessment, requested_mode="fast", policy="allow")
    assert allow["action"] == "allow"
    assert allow["execution_mode"] == "step"  # never blind fast batch for complex

    simple = classify_goal_complexity("uptime")
    ok = resolve_fast_complex_action(simple, requested_mode="fast", policy="ask")
    assert ok["action"] == "allow"
    assert ok["execution_mode"] == "fast"


def test_apply_fast_complexity_routing_on_execute_plan():
    plan = {
        "mode": "execute",
        "execution_mode": "fast",
        "assistant_text": "сделаю",
        "commands": [{"cmd": "systemctl status nginx", "why": "check"}],
    }
    decision = apply_fast_complexity_routing(
        user_message="Инцидент production: найди причину 502, почини nginx, verify health",
        requested_mode="fast",
        plan_obj=plan,
        commands_raw=plan["commands"],
        policy="ask",
    )
    assert decision["action"] == "ask"
    assert decision["assistant_text"]

    # Planner already asked — leave alone
    plan_ask = {**plan, "mode": "ask", "assistant_text": "уточните"}
    leave = apply_fast_complexity_routing(
        user_message="Инцидент production: найди причину 502",
        requested_mode="fast",
        plan_obj=plan_ask,
        policy="ask",
    )
    assert leave["action"] == "allow"


def test_fast_planner_prompt_command_cap_above_six():
    system, _user = build_planner_prompt_parts(
        user_message="проверь disk",
        rules_context="",
        terminal_tail="",
        history=None,
        unavailable_cmds=None,
        chat_mode="agent",
        execution_mode="fast",
    )
    assert "10" in system or "до 10" in system
    assert "Максимум 6 команд" not in system
    assert "Nova" in system or "сложн" in system.lower()


def test_nova_history_compaction_and_partial_summary():
    history = []
    for i in range(1, 28):
        history.append({"turn": i, "role": "tool_call", "content": {"tool": "shell", "args": {"command": f"echo {i}"}}})
        history.append(
            {
                "turn": i,
                "role": "tool_result",
                "content": f"ok line {i} exit_code=0 /etc/nginx/nginx.conf",
            }
        )
    compacted = compact_agent_history(history, compact_after=20, keep_recent=8)
    assert compacted[0]["role"] == "summary"
    assert "Сжатый журнал" in compacted[0]["content"]
    assert len(compacted) < len(history)

    summary = build_partial_stop_summary(
        user_message="почини nginx 502",
        history=history,
        stop_reason="max_iterations",
        iterations=30,
        tool_calls=15,
        todos=[{"content": "проверить статус", "status": "in_progress"}],
    )
    assert summary
    assert "Частичный итог" in summary
    assert "лимит шагов" in summary
    assert "nginx" in summary.lower() or "доказательств" in summary.lower() or "ok line" in summary
    assert "Что делать дальше" in summary


def test_nova_provider_unavailable_summary_has_actionable_routing_guidance():
    summary = build_partial_stop_summary(
        user_message="the purpose of the server",
        history=[],
        stop_reason="provider_unavailable",
        iterations=1,
        tool_calls=0,
    )

    assert "LLM-подключение недоступно" in summary
    assert "AI Connections" in summary
    assert "Переключитесь на Nova" not in summary


@pytest.mark.asyncio
async def test_nova_loop_partial_summary_on_max_iterations(monkeypatch):
    """Drive run_agent_loop stop path without LLM: force max_iterations=1 tool then stop."""
    from pydantic import BaseModel, ConfigDict, Field

    from servers.services.terminal_ai.agent.loop import AgentContext, run_agent_loop
    from servers.services.terminal_ai.agent.schemas import AgentStep, ToolResult
    from servers.services.terminal_ai.agent.tools.base import ServerTarget

    class _Args(BaseModel):
        model_config = ConfigDict(extra="ignore")
        command: str = Field(default="true")

    class _Shell:
        name = "shell"
        description = "shell"
        args_schema = _Args

        async def run(self, args, ctx):
            return ToolResult(ok=True, output="nginx active exit_code=0 /var/log/nginx/error.log")

    class _Done:
        name = "done"
        description = "done"
        args_schema = _Args

        async def run(self, args, ctx):
            return ToolResult(ok=True, output="done")

    call_count = {"n": 0}

    async def fake_llm(system_prompt, user_prompt, **_kwargs):
        call_count["n"] += 1
        # Never emit done — force budget stop after max_iterations tools.
        return AgentStep(thinking="работаю", tool="shell", args={"command": "true"}, final_text="")

    monkeypatch.setattr(
        "servers.services.terminal_ai.agent.loop._llm_next_step_with_retry",
        fake_llm,
    )

    primary = ServerTarget(
        name="primary",
        server_id=1,
        display_name="srv",
        host="127.0.0.1",
        ssh_conn=None,
    )
    ctx = AgentContext(
        user_message="почини nginx и проверь",
        primary=primary,
        max_iterations=3,
        total_timeout_sec=60,
        compact_after_turns=50,
    )
    tools = {"shell": _Shell(), "done": _Done()}
    result = await run_agent_loop(ctx, tools)
    assert result.stopped
    assert result.stop_reason == "max_iterations"
    assert result.final_text
    assert "Частичный итог" in result.final_text
    assert result.iterations == 3


def test_multi_structured_handoff_and_verification_plan():
    task = {
        "id": 1,
        "name": "Restart nginx",
        "role": "deploy_operator",
        "status": "done",
        "description": "restart and fix config",
        "error": "",
        "verification_summary": "",
    }
    result = "systemctl restart nginx; config /etc/nginx/nginx.conf exit_code=0"
    facts = extract_handoff_facts(result)
    assert any("nginx" in f or "path:" in f or "exit_code" in f for f in facts)

    handoff = build_task_handoff(task, result)
    assert handoff["facts"]
    assert handoff["result_excerpt"]

    ctx = append_structured_task_context("", task, result)
    assert "Задача 1" in ctx
    assert "Факты:" in ctx or "path:" in ctx or "service:" in ctx
    assert task.get("handoff")

    assert plan_mentions_mutation([{"name": "Fix service", "description": "restart nginx", "role": "deploy_operator"}])
    plan = [
        {"name": "Fix", "description": "restart and edit config", "role": "deploy_operator"},
    ]
    ensured = ensure_verification_task(plan, max_tasks=15)
    assert len(ensured) == 2
    assert ensured[-1]["role"] == "post_change_verifier"

    already = ensure_verification_task(
        [
            {"name": "Fix", "description": "restart", "role": "deploy_operator"},
            {"name": "Verify", "description": "smoke check", "role": "post_change_verifier"},
        ]
    )
    assert len(already) == 2


def test_multi_config_and_planning_prompt_no_five_to_seven_cap():
    from servers.agents.multi_agent_engine_config import MAX_TASK_ITERATIONS
    from servers.agents.multi_agent_planning import plan_multi_agent_tasks

    assert MAX_TASK_ITERATIONS >= 12
    src = inspect.getsource(plan_multi_agent_tasks)
    assert "5-7" not in src
    assert "10–12" in src or "10-12" in src
    assert "post_change_verifier" in src
    assert "ensure_verification_task" in src


def test_subagent_spec_honors_engine_cap_above_role_default():
    from app.agent_kernel.domain.specs import ToolSpec
    from app.agent_kernel.runtime.subagents import build_task_subagent_spec
    from app.agent_kernel.tools.registry import ToolRegistry

    registry = ToolRegistry(
        {
            "ssh_execute": ToolSpec(
                name="ssh_execute",
                description="ssh",
                category="ssh",
                risk="exec",
                input_schema={},
            )
        }
    )
    spec = build_task_subagent_spec(
        task_name="Investigate logs",
        task_description="read journal and find root cause",
        parent_agent_type="custom",
        parent_goal="fix nginx",
        tool_registry=registry,
        requested_role="log_investigator",
        requested_max_iterations=12,
        max_task_iterations_cap=12,
    )
    assert spec.max_iterations == 12
