"""
Mini-agent executor: runs configured commands on servers via SSH,
then sends output to LLM for analysis.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from app.shell_commands import is_read_only_command
from app.sudo_policy import evaluate_sudo_command, prepare_sudo_command
from app.tools.safety import is_dangerous_command
from core_ui.activity import log_user_activity
from core_ui.audit import audit_context
from servers.agents.agent_analysis import get_ai_analysis
from servers.agents.agent_run_report import build_agent_run_report_payload
from servers.agents.agent_templates import get_all_templates as get_all_templates
from servers.agents.agent_templates import get_template
from servers.models import AgentRun, Server, ServerAgent
from servers.report_delivery import deliver_agent_report_async
from servers.secret_utils import get_server_sudo_secret
from servers.services.agent_command_runner import run_agent_command


def sync_to_async(func, thread_sensitive=False):
    """Wrapper that defaults thread_sensitive=False to avoid CurrentThreadExecutor conflicts."""
    return _s2a(func, thread_sensitive=thread_sensitive)


COMMAND_TIMEOUT = 30
# Wall-clock budget for one mini run (SSH commands + LLM). Prevents zombie "running" rows.
MINI_RUN_WALL_TIMEOUT_SEC = 15 * 60
MINI_AI_ANALYSIS_TIMEOUT_SEC = 180


async def _persist_run(run: AgentRun, *, fields: list[str] | None = None) -> None:
    run.report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
    update_fields = list(fields or [])
    if "report_payload" not in update_fields:
        update_fields.append("report_payload")
    await sync_to_async(run.save)(update_fields=update_fields if fields else None)


async def _finalize_failed_run(
    run: AgentRun, *, message: str, t0: float, outputs: list[dict[str, Any]] | None = None
) -> AgentRun:
    run.status = AgentRun.STATUS_FAILED
    if outputs is not None:
        run.commands_output = outputs
    run.ai_analysis = message
    run.completed_at = timezone.now()
    run.duration_ms = int((time.monotonic() - t0) * 1000)
    await _persist_run(
        run,
        fields=["status", "commands_output", "ai_analysis", "completed_at", "duration_ms", "report_payload"],
    )
    await deliver_agent_report_async(run)
    return run


async def run_agent(
    agent: ServerAgent,
    server: Server,
    user,
    *,
    run_record: AgentRun | None = None,
) -> AgentRun:
    """Execute agent commands on a server and get AI analysis.

    When ``run_record`` is provided (queued execution plane), reuses that row instead
    of creating a new one so HTTP launch can return a run_id immediately.
    """
    t0 = time.monotonic()
    if run_record is None:
        run = await sync_to_async(AgentRun.objects.create)(
            agent=agent,
            server=server,
            user=user,
            status=AgentRun.STATUS_RUNNING,
        )
    else:
        run = run_record
        run.server = server
        run.user = user
        run.status = AgentRun.STATUS_RUNNING
        run.completed_at = None
        run.duration_ms = 0
        await sync_to_async(run.save)(update_fields=["server", "user", "status", "completed_at", "duration_ms"])

    try:
        return await asyncio.wait_for(
            _run_agent_body(agent, server, user, run=run, t0=t0),
            timeout=MINI_RUN_WALL_TIMEOUT_SEC,
        )
    except TimeoutError:
        logger.error(
            "Mini agent '{}' on {} exceeded wall timeout ({}s)",
            agent.name,
            server.name,
            MINI_RUN_WALL_TIMEOUT_SEC,
        )
        return await _finalize_failed_run(
            run,
            message=(f"Mini agent run exceeded wall timeout ({MINI_RUN_WALL_TIMEOUT_SEC}s) and was marked failed."),
            t0=t0,
            outputs=list(run.commands_output or []),
        )


async def _run_agent_body(
    agent: ServerAgent,
    server: Server,
    user,
    *,
    run: AgentRun,
    t0: float,
) -> AgentRun:
    commands = agent.commands or []
    outputs: list[dict[str, Any]] = []

    try:
        sudo_password = await sync_to_async(get_server_sudo_secret)(server)
    except Exception:
        sudo_password = ""

    try:
        for cmd in commands:
            if getattr(server, "ai_read_only", False) and not is_read_only_command(cmd):
                outputs.append(
                    {
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": "BLOCKED: server allows read-only AI commands only",
                        "exit_code": -1,
                        "duration_ms": 0,
                    }
                )
                continue
            if is_dangerous_command(cmd):
                outputs.append(
                    {
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": "BLOCKED: dangerous command detected",
                        "exit_code": -1,
                        "duration_ms": 0,
                    }
                )
                continue
            sudo_decision = evaluate_sudo_command(cmd, agent.sudo_policy)
            if not sudo_decision.allowed:
                outputs.append(
                    {
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": f"BLOCKED: {sudo_decision.reason}",
                        "exit_code": -1,
                        "duration_ms": 0,
                    }
                )
                continue
            try:
                prepared_sudo = prepare_sudo_command(
                    cmd,
                    agent.sudo_policy,
                    sudo_auth_mode=getattr(server, "sudo_auth_mode", "none"),
                    sudo_password=sudo_password,
                )
            except ValueError as exc:
                outputs.append(
                    {
                        "cmd": cmd,
                        "stdout": "",
                        "stderr": f"BLOCKED: {exc}",
                        "exit_code": -1,
                        "duration_ms": 0,
                    }
                )
                continue
            executable_cmd = prepared_sudo.command
            sudo_notes = prepared_sudo.notes

            cmd_t0 = time.monotonic()
            try:
                result = await run_agent_command(
                    server,
                    executable_cmd,
                    input_text=prepared_sudo.input_text,
                    timeout_seconds=COMMAND_TIMEOUT,
                )
                sudo_note_text = ("\n".join(sudo_notes) + "\n") if sudo_notes else ""
                outputs.append(
                    {
                        "cmd": executable_cmd,
                        "stdout": (sudo_note_text + (result.stdout or ""))[:5000],
                        "stderr": (result.stderr or "")[:2000],
                        "exit_code": result.exit_status,
                        "duration_ms": result.duration_ms,
                        "runtime": result.runtime,
                    }
                )
            except TimeoutError:
                outputs.append(
                    {
                        "cmd": executable_cmd,
                        "stdout": "",
                        "stderr": f"TIMEOUT after {COMMAND_TIMEOUT}s",
                        "exit_code": -1,
                        "duration_ms": COMMAND_TIMEOUT * 1000,
                    }
                )
            except Exception as exc:
                outputs.append(
                    {
                        "cmd": executable_cmd,
                        "stdout": "",
                        "stderr": str(exc)[:500],
                        "exit_code": -1,
                        "duration_ms": int((time.monotonic() - cmd_t0) * 1000),
                    }
                )
    except Exception as exc:
        return await _finalize_failed_run(
            run,
            message=f"SSH connection failed: {exc}",
            t0=t0,
            outputs=outputs,
        )

    # Persist command output before LLM so the run page is not empty while AI thinks.
    run.commands_output = outputs
    run.duration_ms = int((time.monotonic() - t0) * 1000)
    await _persist_run(run, fields=["commands_output", "duration_ms", "report_payload"])

    with audit_context(
        user_id=getattr(user, "id", None),
        username_snapshot=str(getattr(user, "username", "") or ""),
        channel="agent",
        path=f"/servers/api/agents/{agent.id}/run/",
        entity_type="agent_run",
        entity_id=str(run.id),
        entity_name=agent.name,
    ):
        try:
            ai_analysis = await asyncio.wait_for(
                get_ai_analysis(
                    agent,
                    server,
                    outputs,
                    template=get_template(agent.agent_type),
                    execution_context=await _mini_execution_context(agent, user, run),
                ),
                timeout=MINI_AI_ANALYSIS_TIMEOUT_SEC,
            )
        except TimeoutError:
            ai_analysis = (
                f"AI analysis timed out after {MINI_AI_ANALYSIS_TIMEOUT_SEC}s. "
                "Command outputs were collected successfully."
            )
            logger.error("AI analysis timed out for mini agent '{}'", agent.name)

    run.status = AgentRun.STATUS_COMPLETED
    run.commands_output = outputs
    run.ai_analysis = ai_analysis
    run.completed_at = timezone.now()
    run.duration_ms = int((time.monotonic() - t0) * 1000)
    await _persist_run(
        run,
        fields=["status", "commands_output", "ai_analysis", "completed_at", "duration_ms", "report_payload"],
    )
    await deliver_agent_report_async(run)

    await sync_to_async(
        lambda: setattr(agent, "last_run_at", timezone.now()) or agent.save(update_fields=["last_run_at"])
    )()

    await sync_to_async(log_user_activity)(
        user=user,
        category="agent",
        action="agent_run",
        entity_type="agent",
        entity_id=str(agent.id),
        entity_name=agent.name,
        description=f"Ran '{agent.name}' on {server.name}: {run.status}",
        metadata={"server_id": server.id, "run_id": run.id, "duration_ms": run.duration_ms},
    )

    logger.info("Agent '{}' on {} -> {} ({}ms)", agent.name, server.name, run.status, run.duration_ms)

    # P3-4: Ingest mini-agent run into memory system
    try:
        from servers.adapters.memory_store import DjangoServerMemoryStore

        _mem_store = DjangoServerMemoryStore()
        summary_parts = [f"Mini-agent '{agent.name}' ({agent.agent_type}) -> {run.status}"]
        for out in outputs[:5]:
            status_icon = "ok" if out.get("exit_code") == 0 else "FAIL"
            summary_parts.append(f"  [{status_icon}] `{out['cmd']}` (exit={out.get('exit_code')})")
        if ai_analysis:
            summary_parts.append(f"AI: {ai_analysis[:300]}")
        await sync_to_async(_mem_store._ingest_event_sync)(
            server.id,
            source_kind="agent_run",
            actor_kind="agent",
            source_ref=f"mini-agent-run:{run.id}",
            session_id=f"mini-agent-run:{run.id}",
            event_type="run_completed" if run.status == AgentRun.STATUS_COMPLETED else "run_failed",
            raw_text="\n".join(summary_parts),
            structured_payload={
                "run_id": run.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_type": agent.agent_type,
                "status": run.status,
                "duration_ms": run.duration_ms,
                "command_count": len(outputs),
            },
            importance_hint=0.75 if run.status == AgentRun.STATUS_COMPLETED else 0.88,
            actor_user_id=getattr(user, "id", None),
            force_compact=True,
        )
    except Exception as mem_exc:
        logger.warning("Mini-agent memory ingestion failed: {}", mem_exc)

    return run


async def _mini_execution_context(agent: ServerAgent, user, run: AgentRun):
    from core_ui.services.ai_execution_context import abuild_execution_context

    context = await abuild_execution_context(
        actor_user_id=user.pk,
        project_id=run.project_id or agent.project_id,
        purpose="opssummary",
        source_kind="agent_run",
        source_id=run.pk,
        mode=run.provider_execution_mode,
        stored_binding=run.provider_binding_snapshot or agent.provider_binding,
        requested_provider="auto",
        provider_session_id=run.provider_session_id,
        idempotency_key=f"agent:{run.pk}:mini-analysis",
        tool_policy={"surface": "mini_agent", "webtrerm_tools_only": True},
    )
    if not run.provider_binding_snapshot:
        run.provider_binding_snapshot = context.binding.to_dict()
        await sync_to_async(run.save)(update_fields=["provider_binding_snapshot"])
    return context


async def run_agent_on_all_servers(
    agent: ServerAgent,
    user,
    *,
    servers: list[Server] | None = None,
    primary_run: AgentRun | None = None,
) -> list[AgentRun]:
    """Run agent on configured servers sequentially.

    ``primary_run`` (if set) is reused for the first server so a pre-created
    queued dispatch row is updated instead of orphaned.
    """
    if servers is None:
        server_ids = await sync_to_async(lambda: list(agent.servers.values_list("id", flat=True)))()
        servers = await sync_to_async(lambda: list(Server.objects.filter(id__in=server_ids)))()

    # Resolve through the package facade so existing integrations that patch
    # ``servers.agents.run_agent`` keep working after the move.
    from servers import agents as agents_api

    runs: list[AgentRun] = []
    for index, srv in enumerate(servers):
        run = await agents_api.run_agent(
            agent,
            srv,
            user,
            run_record=primary_run if index == 0 else None,
        )
        runs.append(run)
    return runs
