from __future__ import annotations

from typing import Any

from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.outcomes import outcome_from_report_payload
from app.pipeline_agent_provider import AgentRunSnapshot
from servers.agents.agent_engine import AgentEngine
from servers.agents.multi_agent_engine import MultiAgentEngine
from servers.models import ServerAgent


def _snapshot_from_agent_run(agent_run) -> AgentRunSnapshot:
    outcome, reason, details = outcome_from_report_payload(getattr(agent_run, "report_payload", None))
    if not outcome:
        status = str(agent_run.status or "")
        if status == "stopped":
            outcome = "stopped"
        elif status == "failed":
            outcome = "failed"
        elif status == "completed":
            outcome = "success"
        else:
            outcome = "failed"
        reason = str(agent_run.ai_analysis or "")[:500]

    plan_summary = details.get("plan_summary") if isinstance(details.get("plan_summary"), dict) else {}
    if not plan_summary and getattr(agent_run, "plan_tasks", None):
        from app.agent_kernel.runtime.outcomes import summarize_plan_tasks

        plan_summary = summarize_plan_tasks(agent_run.plan_tasks)

    tool_call_count = int(details.get("tool_call_count") or 0)
    if not tool_call_count:
        tool_call_count = len(getattr(agent_run, "tool_calls", None) or [])

    failed_task_count = int(details.get("failed_task_count") or 0)
    if not failed_task_count and plan_summary:
        failed_task_count = int(plan_summary.get("failed") or 0)

    policy_blocked_count = int(
        details.get("policy_blocked_count") or getattr(agent_run, "_policy_blocked_count", 0) or 0
    )
    disconnected = list(details.get("disconnected_servers") or getattr(agent_run, "_disconnected_servers", []) or [])

    return AgentRunSnapshot(
        agent_run_id=agent_run.pk,
        status=str(agent_run.status),
        final_report=str(agent_run.final_report or ""),
        ai_analysis=str(agent_run.ai_analysis or ""),
        outcome=outcome,
        outcome_reason=reason,
        tool_call_count=tool_call_count,
        failed_task_count=failed_task_count,
        verification_summary=str(details.get("verification_summary") or ""),
        plan_summary=dict(plan_summary or {}),
        policy_blocked_count=policy_blocked_count,
        disconnected_servers=[str(item) for item in disconnected],
    )


def _apply_engine_runtime_flags(
    engine: Any,
    *,
    unattended: bool,
    pipeline_run_id: int | None,
    require_all_servers: bool,
    execution_approval_granted: bool,
) -> None:
    engine.unattended = bool(unattended)
    engine.pipeline_run_id = pipeline_run_id
    engine.require_all_servers = bool(require_all_servers)
    engine.execution_approval_granted = bool(execution_approval_granted)
    engine._policy_blocked_count = 0
    engine._disconnected_servers = []


async def run_pipeline_react_agent(
    *,
    node_id: str,
    goal: str,
    system_prompt: str,
    instructions: str,
    max_iterations: int,
    tools_config: dict[str, bool],
    servers: list[Any],
    user,
    event_callback,
    model_preference: str,
    specific_model: str | None,
    mcp_servers: list[Any],
    skills: list[Any],
    skill_errors: list[str],
    permission_mode: str = "",
    sudo_policy: str = "",
    unattended: bool = False,
    pipeline_run_id: int | None = None,
    require_all_servers: bool = False,
    execution_approval_granted: bool = False,
) -> AgentRunSnapshot:
    agent = ServerAgent(
        name=f"pipeline_node_{node_id}",
        mode=ServerAgent.MODE_FULL,
        goal=goal,
        system_prompt=system_prompt,
        ai_prompt=instructions,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=len(servers) > 1,
        sudo_policy=sudo_policy,
    )
    engine = AgentEngine(
        agent=agent,
        servers=servers,
        user=user,
        event_callback=event_callback,
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )
    if permission_mode:
        engine.permission_engine = PermissionEngine(mode=permission_mode, sudo_policy=agent.sudo_policy)
    _apply_engine_runtime_flags(
        engine,
        unattended=unattended,
        pipeline_run_id=pipeline_run_id,
        require_all_servers=require_all_servers,
        execution_approval_granted=execution_approval_granted,
    )
    agent_run = await engine.run()
    return _snapshot_from_agent_run(agent_run)


async def run_pipeline_multi_agent(
    *,
    node_id: str,
    goal: str,
    system_prompt: str,
    max_iterations: int,
    tools_config: dict[str, bool],
    servers: list[Any],
    user,
    event_callback,
    model_preference: str,
    specific_model: str | None,
    mcp_servers: list[Any],
    skills: list[Any],
    skill_errors: list[str],
    permission_mode: str = "",
    sudo_policy: str = "",
    instructions: str = "",
    unattended: bool = False,
    pipeline_run_id: int | None = None,
    require_all_servers: bool = True,
    execution_approval_granted: bool = False,
) -> AgentRunSnapshot:
    agent = ServerAgent(
        name=f"pipeline_multi_{node_id}",
        mode=ServerAgent.MODE_MULTI,
        goal=goal,
        system_prompt=system_prompt,
        ai_prompt=instructions or "",
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=True,
        sudo_policy=sudo_policy,
    )
    engine = MultiAgentEngine(
        agent=agent,
        servers=servers,
        user=user,
        event_callback=event_callback,
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )
    if permission_mode:
        engine.permission_engine = PermissionEngine(mode=permission_mode, sudo_policy=agent.sudo_policy)
    _apply_engine_runtime_flags(
        engine,
        unattended=unattended,
        pipeline_run_id=pipeline_run_id,
        require_all_servers=require_all_servers,
        execution_approval_granted=execution_approval_granted,
    )
    agent_run = await engine.run()
    return _snapshot_from_agent_run(agent_run)
