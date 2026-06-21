from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from app.agent_kernel.mcp_runtime import load_mcp_bindings
from app.agent_kernel.tools.registry import ToolRegistry
from servers.agent_runtime import (
    is_runtime_stop_requested,
    register_engine,
    reset_runtime_control_state,
    unregister_engine,
)
from servers.agent_sessions import AgentSessionManager
from servers.agent_tools import AGENT_TOOLS
from servers.models import AgentRun
from servers.multi_agent_plan_executor import execute_plan_tasks
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
        )
    else:
        current_status = await sync_to_async(
            lambda: AgentRun.objects.filter(pk=run_record.pk).values("status", "runtime_control").first()
        )()
        run = run_record
        if not current_status:
            engine.run_record = run
            return run
        if current_status["status"] == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(current_status["runtime_control"]):
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
            plan_tasks=[],
            orchestrator_log=[],
            started_at=timezone.now(),
        )
    engine.run_record = run
    register_engine(run.id, getattr(engine.agent, "id", None), engine)
    engine._control_task = asyncio.create_task(engine._watch_runtime_control())
    await engine._sync_runtime_control()
    t0 = time.monotonic()

    engine.session = AgentSessionManager(
        allowed_servers=engine.servers,
        max_connections=engine.agent.max_connections or 5,
        command_timeout=30,
        event_callback=engine.event_callback,
        available_skills=[skill.to_detail_dict() for skill in engine.skills],
        sudo_policy=engine.permission_engine.sudo_policy,
    )

    plan_tasks: list[dict] = []
    orchestrator_log: list[dict] = []

    try:
        if engine.skill_policy_errors:
            raise RuntimeError(
                "Invalid skill policy configuration: "
                + "; ".join(engine.skill_policy_errors)
            )
        await engine._emit("agent_status", {"status": "connecting"})

        if engine.servers:
            if engine.agent.allow_multi_server:
                for srv in engine.servers:
                    try:
                        await engine.session.open(srv)
                    except Exception as exc:
                        logger.warning("Failed to connect to {}: {}", srv.name, exc)
            else:
                await engine.session.open(primary_server)

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
            agent_tools=AGENT_TOOLS,
        )
        engine.ops_prompt_context = await engine._build_ops_prompt_context()

        connected = engine.session.get_connected_info()
        await sync_to_async(engine._update_run)(run, connected_servers=[
            {"server_id": c["server_id"], "server_name": c["server_name"]}
            for c in connected
        ])

        if not engine.session.connections and not engine.mcp_tools and not engine.skills:
            raise RuntimeError("No servers connected, no MCP tools available, and no skills attached.")

        goal = engine.agent.goal or engine.agent.ai_prompt or "Analyse the servers."

        await engine._emit("agent_status", {"status": "planning"})
        await engine._emit("agent_pipeline_phase", {
            "phase": "planning",
            "message": "Orchestrator is creating a task plan…",
        })

        plan_tasks = await engine._plan(goal, orchestrator_log)

        await sync_to_async(engine._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)
        await engine._emit("agent_plan", {"tasks": plan_tasks})

        if plan_only:
            run.status = AgentRun.STATUS_PLAN_REVIEW
            run.plan_tasks = plan_tasks
            run.orchestrator_log = orchestrator_log
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            await sync_to_async(run.save)()
            await engine._emit("agent_status", {"status": "plan_review"})
            await engine._emit("agent_pipeline_phase", {
                "phase": "plan_review",
                "message": "План готов. Ожидаем подтверждения пользователя…",
            })
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
        await sync_to_async(run.save)()
        await engine._persist_ops_summary(
            run=run,
            final_status=run.status,
            final_report=run.ai_analysis,
            plan_tasks=plan_tasks,
        )
        await deliver_agent_report_async(run)
        await engine._emit("agent_status", {"status": "failed", "error": str(exc)})
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
    if current_status["status"] == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(current_status["runtime_control"]):
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
        command_timeout=30,
        event_callback=engine.event_callback,
        sudo_policy=engine.permission_engine.sudo_policy,
    )

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
            agent_tools=AGENT_TOOLS,
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
        await sync_to_async(run.save)()
        await engine._persist_ops_summary(
            run=run,
            final_status=run.status,
            final_report=run.ai_analysis,
            plan_tasks=plan_tasks,
        )
        await deliver_agent_report_async(run)
        await engine._emit("agent_status", {"status": "failed", "error": str(exc)})
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
    final_report = await engine._synthesize(goal, plan_tasks, orchestrator_log)
    final_report = await engine.hook_manager.run_finished(
        final_report,
        engine.permission_engine.verification_summary(),
    )

    final_status = AgentRun.STATUS_COMPLETED
    if engine._stop_requested:
        final_status = AgentRun.STATUS_STOPPED
    elif any(t["status"] == "failed" for t in plan_tasks):
        final_status = AgentRun.STATUS_COMPLETED

    run.status = final_status
    run.plan_tasks = plan_tasks
    run.orchestrator_log = orchestrator_log
    run.total_iterations = sum(len(t.get("iterations", [])) for t in plan_tasks)
    run.final_report = final_report
    run.ai_analysis = final_report
    run.completed_at = timezone.now()
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    run.duration_ms = int((run.duration_ms or 0) + elapsed_ms) if append_duration else elapsed_ms
    await sync_to_async(run.save)()
    await engine._persist_ops_summary(
        run=run,
        final_status=final_status,
        final_report=final_report,
        plan_tasks=plan_tasks,
    )
    await deliver_agent_report_async(run)

    await sync_to_async(engine._touch_agent_last_run)()
    await engine._emit("agent_status", {"status": final_status})
    await engine._emit("agent_report", {"text": final_report, "interim": False})


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
