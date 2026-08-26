from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from app.agent_kernel.mcp_runtime import load_mcp_bindings
from app.agent_kernel.runtime.outcomes import (
    OUTCOME_FAILED,
    STATUS_FAILED,
    AgentOutcome,
    merge_outcome_into_report_payload,
    resolve_multi_agent_outcome,
)
from app.agent_kernel.tools.registry import ToolRegistry
from servers.agents.agent_run_report import build_agent_run_report_payload
from servers.agents.agent_runtime import (
    execution_binding_snapshot,
    execution_mode_value,
    is_runtime_stop_requested,
    register_engine,
    reset_runtime_control_state,
    unregister_engine,
)
from servers.agents.agent_sessions import AgentSessionManager
from servers.agents.agent_tools import get_all_agent_tools
from servers.agents.multi_agent_plan_executor import execute_plan_tasks
from servers.models import AgentRun
from servers.report_delivery import deliver_agent_report_async


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


async def run_multi_agent_engine(
    engine: Any,
    *,
    plan_only: bool = False,
    run_record: AgentRun | None = None,
) -> AgentRun:
    """Run the full multi-agent pipeline or stop after plan generation."""
    engine._loop = asyncio.get_running_loop()
    primary_server = engine.servers[0] if engine.servers else None
    if run_record is None:
        run = await sync_to_async(AgentRun.objects.create)(
            agent=engine.agent if engine.agent.pk else None,
            server=primary_server,
            user=engine.user,
            status=AgentRun.STATUS_RUNNING,
            runtime_control=reset_runtime_control_state(),
            provider_binding_snapshot=execution_binding_snapshot(engine.execution_context),
            provider_execution_mode=execution_mode_value(engine.execution_context),
        )
    else:
        current_status = await sync_to_async(
            lambda: AgentRun.objects.filter(pk=run_record.pk).values("status", "runtime_control").first()
        )()
        run = run_record
        if not current_status:
            engine.run_record = run
            return run
        if current_status["status"] == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(
            current_status["runtime_control"]
        ):
            engine.run_record = run
            return run
        await sync_to_async(engine._update_run)(
            run,
            agent=engine.agent if engine.agent.pk else None,
            server=primary_server,
            user=engine.user,
            status=AgentRun.STATUS_RUNNING,
            ai_analysis="",
            commands_output=[],
            duration_ms=0,
            completed_at=None,
            total_iterations=0,
            connected_servers=[],
            runtime_control=reset_runtime_control_state(),
            pending_question="",
            final_report="",
            execution_outcome={},
            plan_tasks=[],
            orchestrator_log=[],
            started_at=timezone.now(),
        )
    engine.run_record = run
    register_engine(run.id, getattr(engine.agent, "id", None), engine)
    engine._control_task = asyncio.create_task(engine._watch_runtime_control())
    await engine._sync_runtime_control()
    t0 = time.monotonic()

    from servers.agents.agent_budgets import MULTI_DEFAULT_COMMAND_TIMEOUT_SEC, clamp_command_timeout

    tools_cfg = dict(getattr(engine.agent, "tools_config", None) or {})
    command_timeout = clamp_command_timeout(
        tools_cfg.get("command_timeout")
        or tools_cfg.get("command_timeout_seconds")
        or getattr(engine, "command_timeout", None)
        or MULTI_DEFAULT_COMMAND_TIMEOUT_SEC
    )
    engine.command_timeout = command_timeout
    engine.session = AgentSessionManager(
        allowed_servers=engine.servers,
        max_connections=engine.agent.max_connections or 5,
        command_timeout=command_timeout,
        event_callback=engine.event_callback,
        available_skills=[skill.to_detail_dict() for skill in engine.skills],
        available_materials=list(
            getattr(engine, "input_materials", None) or getattr(engine.agent, "input_artifacts", None) or []
        ),
        sudo_policy=engine.permission_engine.sudo_policy,
        execution_approval_granted=bool(getattr(engine, "execution_approval_granted", False)),
    )
    engine.session.llm_execution_context_provider = engine._execution_context_for

    plan_tasks: list[dict] = []
    orchestrator_log: list[dict] = []

    try:
        if engine.skill_policy_errors:
            raise RuntimeError("Invalid skill policy configuration: " + "; ".join(engine.skill_policy_errors))
        await engine._emit("agent_status", {"status": "connecting"})

        disconnected: list[str] = []
        if engine.servers:
            if engine.agent.allow_multi_server:
                for srv in engine.servers:
                    try:
                        await engine.session.open(srv)
                    except Exception as exc:
                        logger.warning("Failed to connect to {}: {}", srv.name, exc)
                        disconnected.append(str(srv.name))
            else:
                await engine.session.open(primary_server)
        engine._disconnected_servers = disconnected
        if disconnected and bool(getattr(engine, "require_all_servers", True)):
            raise RuntimeError("require_all_servers: failed to connect to: " + ", ".join(disconnected))

        loaded_mcp_tools, engine.mcp_tool_errors = await load_mcp_bindings(
            engine._mcp_runtime_provider,
            engine.mcp_servers,
        )
        if engine.allowed_tool_names is None:
            engine.mcp_tools = loaded_mcp_tools
            engine.disabled_mcp_tools = set()
        else:
            engine.mcp_tools = {
                name: binding for name, binding in loaded_mcp_tools.items() if name in engine.allowed_tool_names
            }
            engine.disabled_mcp_tools = set(loaded_mcp_tools) - set(engine.mcp_tools)
        engine.tool_registry = ToolRegistry.from_sources(
            engine.enabled_tools,
            engine.mcp_tools,
            agent_tools=get_all_agent_tools(),
        )
        engine.ops_prompt_context = await engine._build_ops_prompt_context()

        connected = engine.session.get_connected_info()
        await sync_to_async(engine._update_run)(
            run, connected_servers=[{"server_id": c["server_id"], "server_name": c["server_name"]} for c in connected]
        )

        goal = engine.agent.goal or engine.agent.ai_prompt or "Complete the assigned task."

        await engine._emit("agent_status", {"status": "planning"})
        await engine._emit(
            "agent_pipeline_phase",
            {
                "phase": "planning",
                "message": "Orchestrator is creating a task plan…",
            },
        )

        plan_tasks = await engine._plan(goal, orchestrator_log)

        await sync_to_async(engine._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)
        await engine._emit("agent_plan", {"tasks": plan_tasks})

        if plan_only:
            run.status = AgentRun.STATUS_PLAN_REVIEW
            run.plan_tasks = plan_tasks
            run.orchestrator_log = orchestrator_log
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            run.report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
            await sync_to_async(run.save)()
            await engine._emit("agent_status", {"status": "plan_review"})
            await engine._emit(
                "agent_pipeline_phase",
                {
                    "phase": "plan_review",
                    "message": "План готов. Ожидаем подтверждения пользователя…",
                },
            )
            return run

        deadline = time.monotonic() + engine.session_timeout
        await execute_plan_tasks(
            goal=goal,
            plan_tasks=plan_tasks,
            orchestrator_log=orchestrator_log,
            deadline=deadline,
            callbacks=engine._build_plan_execution_callbacks(run),
            skip_completed=True,
        )

        await _finalize_multi_agent_run(engine, run, goal, plan_tasks, orchestrator_log, t0)

    except Exception as exc:
        logger.exception("MultiAgentEngine error: {}", exc)
        run.status = AgentRun.STATUS_FAILED
        run.ai_analysis = f"Pipeline failed: {exc}"
        run.plan_tasks = plan_tasks
        run.orchestrator_log = orchestrator_log
        run.completed_at = timezone.now()
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        failed_outcome = AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason=f"Pipeline failed: {exc}",
            failed_task_count=sum(1 for t in plan_tasks if t.get("status") == "failed"),
            plan_summary=resolve_multi_agent_outcome(
                stop_requested=False,
                plan_tasks=plan_tasks,
            ).plan_summary,
            exit_reason="exception",
        )
        report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
        run.report_payload = merge_outcome_into_report_payload(report_payload, failed_outcome)
        run.execution_outcome = {
            **failed_outcome.to_payload(),
            "report_generation": {"status": "failed", "generated_at": None, "error": run.ai_analysis},
        }
        await sync_to_async(run.save)()
        await engine._persist_ops_summary(
            run=run,
            final_status=run.status,
            final_report=run.ai_analysis,
            plan_tasks=plan_tasks,
        )
        await deliver_agent_report_async(run)
        await engine._emit("agent_status", {"status": "failed", "error": str(exc), "outcome": "failed"})
    finally:
        await _cleanup_multi_agent_run(engine, run)

    return run


async def execute_existing_multi_agent_plan(engine: Any, run: AgentRun) -> AgentRun:
    """Execute Phase 2 and Phase 3 for a plan_review run."""
    engine._loop = asyncio.get_running_loop()
    current_status = await sync_to_async(
        lambda: AgentRun.objects.filter(pk=run.pk).values("status", "runtime_control").first()
    )()
    if not current_status:
        engine.run_record = run
        return run
    if current_status["status"] == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(
        current_status["runtime_control"]
    ):
        engine.run_record = run
        return run
    engine.run_record = run
    register_engine(run.id, getattr(engine.agent, "id", None), engine)
    engine._control_task = asyncio.create_task(engine._watch_runtime_control())
    await engine._sync_runtime_control()
    plan_tasks: list[dict] = list(run.plan_tasks or [])
    orchestrator_log: list[dict] = list(run.orchestrator_log or [])
    primary_server = engine.servers[0]
    t0 = time.monotonic()

    engine.session = AgentSessionManager(
        allowed_servers=engine.servers,
        max_connections=engine.agent.max_connections or 5,
        command_timeout=int(getattr(engine, "command_timeout", 90) or 90),
        event_callback=engine.event_callback,
        available_skills=[skill.to_detail_dict() for skill in engine.skills],
        available_materials=list(
            getattr(engine, "input_materials", None) or getattr(engine.agent, "input_artifacts", None) or []
        ),
        sudo_policy=engine.permission_engine.sudo_policy,
        execution_approval_granted=bool(getattr(engine, "execution_approval_granted", False)),
    )
    engine.session.llm_execution_context_provider = engine._execution_context_for

    try:
        await engine._emit("agent_status", {"status": "connecting"})

        if engine.agent.allow_multi_server:
            for srv in engine.servers:
                try:
                    await engine.session.open(srv)
                except Exception as exc:
                    logger.warning("Failed to connect to {}: {}", srv.name, exc)
        else:
            await engine.session.open(primary_server)

        if not engine.session.connections:
            raise RuntimeError("No servers connected.")

        engine.tool_registry = ToolRegistry.from_sources(
            engine.enabled_tools,
            engine.mcp_tools,
            agent_tools=get_all_agent_tools(),
        )
        engine.ops_prompt_context = await engine._build_ops_prompt_context()
        await sync_to_async(engine._update_run)(run, status=AgentRun.STATUS_RUNNING)
        await engine._emit("agent_status", {"status": "running"})
        await engine._emit("agent_pipeline_phase", {"phase": "executing", "message": "Выполняю задачи пайплайна…"})

        goal = engine.agent.goal or engine.agent.ai_prompt or "Analyse the servers."

        deadline = time.monotonic() + engine.session_timeout
        await execute_plan_tasks(
            goal=goal,
            plan_tasks=plan_tasks,
            orchestrator_log=orchestrator_log,
            deadline=deadline,
            callbacks=engine._build_plan_execution_callbacks(run),
            skip_completed=True,
        )

        await _finalize_multi_agent_run(
            engine,
            run,
            goal,
            plan_tasks,
            orchestrator_log,
            t0,
            append_duration=True,
        )

    except Exception as exc:
        logger.exception("MultiAgentEngine execute_existing_plan error: {}", exc)
        run.status = AgentRun.STATUS_FAILED
        run.ai_analysis = f"Pipeline failed: {exc}"
        run.plan_tasks = plan_tasks
        run.orchestrator_log = orchestrator_log
        run.completed_at = timezone.now()
        run.duration_ms = int((run.duration_ms or 0) + (time.monotonic() - t0) * 1000)
        failed_outcome = AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason=f"Pipeline failed: {exc}",
            failed_task_count=sum(1 for t in plan_tasks if t.get("status") == "failed"),
            plan_summary=resolve_multi_agent_outcome(
                stop_requested=False,
                plan_tasks=plan_tasks,
            ).plan_summary,
            exit_reason="exception",
        )
        report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
        run.report_payload = merge_outcome_into_report_payload(report_payload, failed_outcome)
        run.execution_outcome = {
            **failed_outcome.to_payload(),
            "report_generation": {"status": "failed", "generated_at": None, "error": run.ai_analysis},
        }
        await sync_to_async(run.save)()
        await engine._persist_ops_summary(
            run=run,
            final_status=run.status,
            final_report=run.ai_analysis,
            plan_tasks=plan_tasks,
        )
        await deliver_agent_report_async(run)
        await engine._emit("agent_status", {"status": "failed", "error": str(exc), "outcome": "failed"})
    finally:
        await _cleanup_multi_agent_run(engine, run)

    return run


async def _finalize_multi_agent_run(
    engine: Any,
    run: AgentRun,
    goal: str,
    plan_tasks: list[dict],
    orchestrator_log: list[dict],
    t0: float,
    *,
    append_duration: bool = False,
) -> None:
    await engine._emit("agent_pipeline_phase", {"phase": "synthesizing", "message": "Generating final report…"})
    verification_summary = engine.permission_engine.verification_summary()
    final_report = await engine._synthesize(goal, plan_tasks, orchestrator_log)
    final_report = await engine.hook_manager.run_finished(
        final_report,
        verification_summary,
    )

    outcome = resolve_multi_agent_outcome(
        stop_requested=bool(engine._stop_requested),
        plan_tasks=plan_tasks,
        verification_summary=verification_summary,
        pending_verifications=getattr(engine.permission_engine, "pending_verifications", set()),
    )
    final_status = outcome.status
    if outcome.outcome != "success" and outcome.reason:
        final_report = f"{final_report}\n\n---\nOutcome: {outcome.outcome} — {outcome.reason}".strip()

    run.status = final_status
    run.plan_tasks = plan_tasks
    run.orchestrator_log = orchestrator_log
    run.total_iterations = sum(len(t.get("iterations", [])) for t in plan_tasks)
    run.final_report = final_report
    if final_status == AgentRun.STATUS_COMPLETED:
        run.ai_analysis = final_report
    else:
        run.ai_analysis = outcome.reason or final_report
    run.completed_at = timezone.now()
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    run.duration_ms = int((run.duration_ms or 0) + elapsed_ms) if append_duration else elapsed_ms
    report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
    report_payload = merge_outcome_into_report_payload(report_payload, outcome)
    report_payload["policy_blocked_count"] = int(getattr(engine, "_policy_blocked_count", 0) or 0)
    report_payload["disconnected_servers"] = list(getattr(engine, "_disconnected_servers", []) or [])
    execution_outcome = outcome.to_payload()
    execution_outcome["policy_blocked_count"] = report_payload["policy_blocked_count"]
    execution_outcome["disconnected_servers"] = report_payload["disconnected_servers"]
    execution_outcome["report_generation"] = {
        "status": "ready" if final_report else "failed",
        "generated_at": run.completed_at.isoformat() if final_report and run.completed_at else None,
        "error": "" if final_report else "Final report is empty.",
    }
    run.execution_outcome = execution_outcome
    details = report_payload.get("outcome_details")
    if isinstance(details, dict):
        details = dict(details)
        details["policy_blocked_count"] = report_payload["policy_blocked_count"]
        details["disconnected_servers"] = report_payload["disconnected_servers"]
        report_payload["outcome_details"] = details
    run.report_payload = report_payload
    await sync_to_async(run.save)()
    await engine._persist_ops_summary(
        run=run,
        final_status=final_status,
        final_report=final_report,
        plan_tasks=plan_tasks,
    )
    await deliver_agent_report_async(run)

    await sync_to_async(engine._touch_agent_last_run)()
    await engine._emit(
        "agent_status",
        {
            "status": final_status,
            "outcome": outcome.outcome,
            "outcome_reason": outcome.reason,
            "plan_summary": outcome.plan_summary,
            "policy_blocked_count": report_payload["policy_blocked_count"],
        },
    )
    await engine._emit(
        "agent_report",
        {
            "text": final_report,
            "interim": False,
            "outcome": outcome.outcome,
        },
    )


async def _cleanup_multi_agent_run(engine: Any, run: AgentRun) -> None:
    unregister_engine(run.id, engine)
    if engine._control_task:
        engine._control_task.cancel()
        with suppress(asyncio.CancelledError):
            await engine._control_task
        engine._control_task = None
    engine._loop = None
    if engine.session:
        await engine.session.close_all()
