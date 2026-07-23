"""
Mini-agent executor: runs configured commands on servers via SSH,
then sends output to LLM for analysis.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from app.sudo_policy import evaluate_sudo_command, prepare_sudo_command
from app.tools.safety import is_dangerous_command
from core_ui.activity import log_user_activity
from core_ui.audit import audit_context
from servers.agent_analysis import get_ai_analysis
from servers.agent_run_report import build_agent_run_report_payload
from servers.agent_templates import get_all_templates as get_all_templates
from servers.agent_templates import get_template
from servers.models import AgentRun, Server, ServerAgent
from servers.monitor import _build_connect_kwargs
from servers.report_delivery import deliver_agent_report_async
from servers.secret_utils import get_server_sudo_secret


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
        kwargs = await _build_connect_kwargs(server)
    except Exception as exc:
        return await _finalize_failed_run(run, message=f"Cannot connect to server: {exc}", t0=t0)

    try:
        sudo_password = await sync_to_async(get_server_sudo_secret)(server)
    except Exception:
        sudo_password = ""

    try:
        async with asyncssh.connect(**kwargs) as conn:
            for cmd in commands:
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
                    run_kwargs: dict[str, Any] = {"check": False}
                    if prepared_sudo.input_text is not None:
                        run_kwargs["input"] = prepared_sudo.input_text
                    result = await asyncio.wait_for(
                        conn.run(executable_cmd, **run_kwargs),
                        timeout=COMMAND_TIMEOUT,
                    )
                    sudo_note_text = ("\n".join(sudo_notes) + "\n") if sudo_notes else ""
                    outputs.append(
                        {
                            "cmd": executable_cmd,
                            "stdout": (sudo_note_text + (result.stdout or ""))[:5000],
                            "stderr": (result.stderr or "")[:2000],
                            "exit_code": result.exit_status,
                            "duration_ms": int((time.monotonic() - cmd_t0) * 1000),
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
                get_ai_analysis(agent, server, outputs, template=get_template(agent.agent_type)),
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

    runs: list[AgentRun] = []
    for index, srv in enumerate(servers):
        run = await run_agent(
            agent,
            srv,
            user,
            run_record=primary_run if index == 0 else None,
        )
        runs.append(run)
    return runs
