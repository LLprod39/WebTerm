"""Final report persistence + exception failure path for agent engine runs."""

from __future__ import annotations

import time
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone
from loguru import logger

from app.agent_kernel.runtime.outcomes import (
    OUTCOME_FAILED,
    STATUS_FAILED,
    AgentOutcome,
    merge_outcome_into_report_payload,
    resolve_react_outcome,
)
from servers.agents.agent_run_report import build_agent_run_report_payload
from servers.models import AgentRun
from servers.report_delivery import deliver_agent_report_async


async def finalize_successful_run(
    engine: Any,
    *,
    run: AgentRun,
    exit_reason: str,
    tools_available: bool,
    tool_calls_log: list[dict],
    iterations_log: list[dict],
    history: list[dict],
    iteration: int,
    t0: float,
) -> None:
    verification_summary = engine.permission_engine.verification_summary()
    outcome = resolve_react_outcome(
        exit_reason=exit_reason,
        tool_calls=tool_calls_log,
        tools_available=tools_available,
        pending_verifications=getattr(engine.permission_engine, "pending_verifications", set()),
        verification_summary=verification_summary,
    )
    final_status = outcome.status

    logger.info(
        "agent_run {} generating final report: final_status={} outcome={} exit_reason={} iterations={}",
        run.pk,
        final_status,
        outcome.outcome,
        exit_reason,
        iteration,
    )
    final_report = await engine._generate_final_report(history, iterations_log)
    final_report = await engine.hook_manager.run_finished(
        final_report,
        verification_summary,
    )
    if outcome.outcome != "success" and outcome.reason:
        # Keep report readable while making partial/fail reason explicit.
        final_report = f"{final_report}\n\n---\nOutcome: {outcome.outcome} — {outcome.reason}".strip()

    run.status = final_status
    run.iterations_log = iterations_log
    run.tool_calls = tool_calls_log
    run.total_iterations = iteration
    run.final_report = final_report
    run.ai_analysis = (
        final_report
        if final_status == AgentRun.STATUS_COMPLETED
        else (outcome.reason or final_report or f"Agent ended with status {final_status}")
    )
    run.completed_at = timezone.now()
    run.duration_ms = int((time.monotonic() - t0) * 1000)
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
        iterations_log=iterations_log,
        tool_calls_log=tool_calls_log,
    )
    await deliver_agent_report_async(run)
    logger.info(
        "agent_run {} saved: status={} outcome={} duration_ms={} report_chars={}",
        run.pk,
        run.status,
        outcome.outcome,
        run.duration_ms,
        len(final_report or ""),
    )

    await sync_to_async(engine._touch_agent_last_run)()

    await engine._emit(
        "agent_status",
        {
            "status": final_status,
            "outcome": outcome.outcome,
            "outcome_reason": outcome.reason,
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


async def finalize_failed_run(
    engine: Any,
    *,
    run: AgentRun,
    exc: BaseException,
    tool_calls_log: list[dict],
    iterations_log: list[dict],
    t0: float,
) -> None:
    logger.error("Agent engine error: {}", exc)
    # Some exceptions (asyncio.TimeoutError / CancelledError) stringify to "",
    # which produced an unhelpful bare "Agent failed:" in the report.
    exc_text = str(exc).strip() or type(exc).__name__
    run.status = AgentRun.STATUS_FAILED
    run.ai_analysis = f"Agent failed: {exc_text}"
    run.iterations_log = iterations_log
    run.tool_calls = tool_calls_log
    run.total_iterations = len(iterations_log)
    run.completed_at = timezone.now()
    run.duration_ms = int((time.monotonic() - t0) * 1000)
    # Hard exception is always a failed run.
    failed_outcome = AgentOutcome(
        outcome=OUTCOME_FAILED,
        status=STATUS_FAILED,
        reason=f"Agent failed: {exc_text}",
        tool_call_count=len(tool_calls_log),
        verification_summary=exc_text,
        exit_reason="exception",
    )
    report_payload = await sync_to_async(build_agent_run_report_payload, thread_sensitive=True)(run)
    run.report_payload = merge_outcome_into_report_payload(report_payload, failed_outcome)
    run.execution_outcome = {
        **failed_outcome.to_payload(),
        "report_generation": {
            "status": "failed",
            "generated_at": None,
            "error": run.ai_analysis,
        },
    }
    await sync_to_async(run.save)()
    await engine._persist_ops_summary(
        run=run,
        final_status=run.status,
        final_report=run.ai_analysis,
        iterations_log=iterations_log,
        tool_calls_log=tool_calls_log,
    )
    await deliver_agent_report_async(run)
    await engine._emit("agent_status", {"status": "failed", "error": exc_text, "outcome": "failed"})
