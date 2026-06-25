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
from app.execution_policy import safe_payload_preview
from servers.agent_run_report import build_agent_run_report_payload
from servers.agent_runtime import (
    is_runtime_stop_requested,
    register_engine,
    reset_runtime_control_state,
    unregister_engine,
)
from servers.agent_sessions import AgentSessionManager
from servers.agent_tools import AGENT_TOOLS
from servers.models import AgentRun
from servers.report_delivery import deliver_agent_report_async


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


async def run_agent_engine(engine: Any, run_record: AgentRun | None = None) -> AgentRun:
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
            iterations_log=[],
            tool_calls=[],
            total_iterations=0,
            connected_servers=[],
            runtime_control=reset_runtime_control_state(),
            pending_question="",
            final_report="",
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

    iterations_log: list[dict] = []
    tool_calls_log: list[dict] = []
    history: list[dict[str, str]] = []

    try:
        logger.info(
            "agent_run {} start: agent='{}' servers={} mcp_servers={} skills={} provider={} model={}",
            run.pk,
            engine.agent.name,
            [srv.name for srv in engine.servers],
            [srv.name for srv in engine.mcp_servers],
            [skill.slug for skill in engine.skills],
            engine.model_preference,
            engine.specific_model,
        )
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

        loaded_mcp_tools, engine.mcp_tool_errors = await load_mcp_bindings(engine._mcp_runtime_provider, engine.mcp_servers)
        if engine.allowed_tool_names is None:
            engine.mcp_tools = loaded_mcp_tools
            engine.disabled_mcp_tools = set()
        else:
            engine.mcp_tools = {
                name: binding for name, binding in loaded_mcp_tools.items() if name in engine.allowed_tool_names
            }
            engine.disabled_mcp_tools = set(loaded_mcp_tools) - set(engine.mcp_tools)
        logger.info(
            "agent_run {} mcp bindings loaded: tools={} errors={}",
            run.pk,
            sorted(engine.mcp_tools.keys()),
            engine.mcp_tool_errors,
        )

        connected = engine.session.get_connected_info()
        await sync_to_async(engine._update_run)(run, connected_servers=[
            {"server_id": c["server_id"], "server_name": c["server_name"]}
            for c in connected
        ])

        if not engine.session.connections and not engine.mcp_tools and not engine.skills:
            raise RuntimeError("No servers connected, no MCP tools available, and no skills attached.")

        engine.tool_registry = ToolRegistry.from_sources(
            engine.enabled_tools,
            engine.mcp_tools,
            agent_tools=AGENT_TOOLS,
        )
        engine.ops_prompt_context = await engine._build_ops_prompt_context()
        system_prompt = engine._build_system_prompt()
        history.append({"role": "system", "content": system_prompt})

        # GAP 4: on_agent_start hook
        await engine.hook_manager.on_agent_start(
            run_id=str(run.pk),
            server_id=primary_server.id if primary_server else None,
            goal=engine.agent.goal or engine.agent.ai_prompt or "",
            role=engine.role_spec.slug,
            permission_mode=str(engine.permission_engine.mode),
        )

        goal = engine.agent.goal or engine.agent.ai_prompt or "Analyze the servers."
        history.append({"role": "user", "content": f"Goal: {goal}"})

        await engine._emit("agent_status", {"status": "thinking", "iteration": 0})

        iteration = 0
        deadline = time.monotonic() + engine.session_timeout

        while iteration < engine.max_iterations:
            if engine._stop_requested:
                await engine._emit("agent_status", {"status": "stopped"})
                break

            await engine._pause_event.wait()

            if time.monotonic() > deadline:
                await engine._emit("agent_status", {"status": "timeout"})
                break

            iteration += 1
            logger.info("agent_run {} iteration {} start", run.pk, iteration)
            await engine._emit("agent_status", {"status": "thinking", "iteration": iteration})

            try:
                llm_response = await engine._call_llm(history)
            except Exception as llm_exc:
                logger.error("agent_run {} iteration {} LLM call error: {}", run.pk, iteration, llm_exc)
                await engine._emit("agent_status", {"status": "llm_error", "error": str(llm_exc)})
                break
            if not llm_response:
                logger.warning("agent_run {} iteration {} got empty llm response", run.pk, iteration)
                break

            thought, action_name, action_args = engine._parse_response(llm_response)
            logger.info(
                "agent_run {} iteration {} parsed action: action={} args={} thought={}",
                run.pk,
                iteration,
                action_name,
                safe_payload_preview(action_args),
                (thought or "")[:300],
            )

            iter_entry = {
                "iteration": iteration,
                "thought": thought,
                "action": action_name,
                "args": action_args,
                "observation": "",
                "timestamp": timezone.now().isoformat(),
            }

            await engine._emit("agent_thought", {"iteration": iteration, "thought": thought})

            if action_name is None:
                if engine._should_reprompt_missing_action(llm_response, tool_calls_log):
                    correction = engine._missing_action_correction()
                    logger.warning(
                        "agent_run {} iteration {} missing ACTION despite tool intent; reprompting",
                        run.pk,
                        iteration,
                    )
                    iter_entry["observation"] = correction
                    iterations_log.append(iter_entry)
                    history.append({"role": "assistant", "content": llm_response})
                    history.append({"role": "user", "content": correction})
                    await engine._emit("agent_observation", {
                        "iteration": iteration,
                        "tool": "parser_guard",
                        "observation": correction,
                    })
                    continue

                logger.info("agent_run {} iteration {} completed with final answer", run.pk, iteration)
                iter_entry["observation"] = "(final answer)"
                iterations_log.append(iter_entry)
                history.append({"role": "assistant", "content": llm_response})
                break

            await engine._emit("agent_action", {
                "iteration": iteration,
                "tool": action_name,
                "args": action_args,
            })

            if action_name == "ask_user":
                await sync_to_async(engine._update_run)(
                    run, status=AgentRun.STATUS_WAITING,
                    pending_question=action_args.get("question", ""),
                )

            observation = await engine._execute_tool(action_name, action_args)
            logger.info(
                "agent_run {} iteration {} tool result: tool={} chars={}",
                run.pk,
                iteration,
                action_name,
                len(observation or ""),
            )

            if action_name == "ask_user":
                await sync_to_async(engine._update_run)(
                    run, status=AgentRun.STATUS_RUNNING, pending_question="",
                )

            tool_calls_log.append({
                "tool": action_name,
                "args": action_args,
                "result": observation[:2000],
                "duration_ms": 0,
                "timestamp": timezone.now().isoformat(),
            })

            iter_entry["observation"] = observation[:3000]
            iterations_log.append(iter_entry)

            # GAP 4: on_iteration_complete hook
            await engine.hook_manager.on_iteration_complete(
                iteration=iteration,
                thought=thought or "",
                action=action_name or "",
                tool=action_name or "",
                observation=observation[:400],
            )

            # GAP 4: budget warning at 75%
            if iteration == max(1, int(engine.max_iterations * 0.75)):
                await engine.hook_manager.on_run_budget_warning(
                    iterations_used=iteration,
                    iterations_max=engine.max_iterations,
                    remaining_fraction=1.0 - iteration / engine.max_iterations,
                )

            await engine._emit("agent_observation", {
                "iteration": iteration,
                "tool": action_name,
                "observation": observation[:1000],
            })

            history.append({"role": "assistant", "content": llm_response})
            history.append(
                {
                    "role": "user",
                    "content": engine.hook_manager.build_observation_message(observation, limit=4000),
                }
            )

        final_status = AgentRun.STATUS_COMPLETED
        if engine._stop_requested:
            final_status = AgentRun.STATUS_STOPPED
        elif time.monotonic() > deadline:
            final_status = AgentRun.STATUS_FAILED

        logger.info(
            "agent_run {} generating final report: final_status={} iterations={}",
            run.pk,
            final_status,
            iteration,
        )
        final_report = await engine._generate_final_report(history, iterations_log)
        final_report = await engine.hook_manager.run_finished(
            final_report,
            engine.permission_engine.verification_summary(),
        )

        run.status = final_status
        run.iterations_log = iterations_log
        run.tool_calls = tool_calls_log
        run.total_iterations = iteration
        run.final_report = final_report
        run.ai_analysis = final_report
        run.completed_at = timezone.now()
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        run.report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
        await sync_to_async(run.save)()
        await engine._persist_ops_summary(
            run=run,
            final_status=final_status,
            final_report=final_report,
            iterations_log=iterations_log,
            tool_calls_log=tool_calls_log,
        )
        await deliver_agent_report_async(run)
        logger.info(
            "agent_run {} saved: status={} duration_ms={} report_chars={}",
            run.pk,
            run.status,
            run.duration_ms,
            len(final_report or ""),
        )

        await sync_to_async(engine._touch_agent_last_run)()

        await engine._emit("agent_status", {"status": final_status})
        await engine._emit("agent_report", {"text": final_report, "interim": False})

    except Exception as exc:
        logger.error("Agent engine error: {}", exc)
        run.status = AgentRun.STATUS_FAILED
        run.ai_analysis = f"Agent failed: {exc}"
        run.iterations_log = iterations_log
        run.tool_calls = tool_calls_log
        run.total_iterations = len(iterations_log)
        run.completed_at = timezone.now()
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        run.report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
        await sync_to_async(run.save)()
        await engine._persist_ops_summary(
            run=run,
            final_status=run.status,
            final_report=run.ai_analysis,
            iterations_log=iterations_log,
            tool_calls_log=tool_calls_log,
        )
        await deliver_agent_report_async(run)
        await engine._emit("agent_status", {"status": "failed", "error": str(exc)})
    finally:
        unregister_engine(run.id, engine)
        if engine._control_task:
            engine._control_task.cancel()
            with suppress(asyncio.CancelledError):
                await engine._control_task
            engine._control_task = None
        engine._loop = None
        if engine.session:
            await engine.session.close_all()

    return run
