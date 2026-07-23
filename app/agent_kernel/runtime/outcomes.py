"""Agent run outcome semantics for ReAct / multi-agent engines and pipelines.

Outcomes are more precise than AgentRun.status:
- success  — goal finished with evidence
- partial  — work happened but goal not fully proven
- failed   — hard failure / timeout / abort / no capacity
- stopped  — operator stop

AgentRun.status stays within existing enum values; outcome is stored in
report_payload and returned via AgentRunSnapshot for pipeline mapping.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

OUTCOME_SUCCESS = "success"
OUTCOME_PARTIAL = "partial"
OUTCOME_FAILED = "failed"
OUTCOME_STOPPED = "stopped"

# AgentRun.status values (strings, avoid Django import in kernel)
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_STOPPED = "stopped"

EXIT_FINAL_ANSWER = "final_answer"
EXIT_STOPPED = "stopped"
EXIT_TIMEOUT = "timeout"
EXIT_MAX_ITERATIONS = "max_iterations"
EXIT_EMPTY_LLM = "empty_llm"
EXIT_LLM_ERROR = "llm_error"

ON_PARTIAL_ERROR = "error"
ON_PARTIAL_SUCCESS = "success"
ON_PARTIAL_ABORT = "abort"


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    """Resolved terminal outcome for an agent run."""

    outcome: str
    status: str
    reason: str
    tool_call_count: int = 0
    failed_task_count: int = 0
    done_task_count: int = 0
    skipped_task_count: int = 0
    pending_task_count: int = 0
    pending_verifications: tuple[str, ...] = ()
    plan_summary: dict[str, int] = field(default_factory=dict)
    verification_summary: str = ""
    exit_reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["pending_verifications"] = list(self.pending_verifications)
        return data


def summarize_plan_tasks(plan_tasks: list[dict[str, Any]] | None) -> dict[str, int]:
    counts = {
        "total": 0,
        "done": 0,
        "failed": 0,
        "skipped": 0,
        "pending": 0,
        "running": 0,
        "stopped": 0,
        "other": 0,
    }
    for task in plan_tasks or []:
        counts["total"] += 1
        status = str(task.get("status") or "").strip().lower()
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts


def resolve_react_outcome(
    *,
    exit_reason: str,
    tool_calls: list[dict[str, Any]] | None,
    tools_available: bool,
    pending_verifications: set[str] | list[str] | tuple[str, ...] | None = None,
    verification_summary: str = "",
) -> AgentOutcome:
    """Map ReAct loop exit conditions to status + outcome."""
    tool_call_count = len(tool_calls or [])
    pending = tuple(sorted(str(item) for item in (pending_verifications or []) if item))
    reason_base = {
        EXIT_STOPPED: "Agent stopped by operator",
        EXIT_TIMEOUT: "Agent session timed out",
        EXIT_MAX_ITERATIONS: "Max iterations exhausted without proven completion",
        EXIT_EMPTY_LLM: "Empty LLM response",
        EXIT_LLM_ERROR: "LLM call failed",
        EXIT_FINAL_ANSWER: "Agent returned a final answer",
    }.get(exit_reason, f"Exit reason: {exit_reason or 'unknown'}")

    if exit_reason == EXIT_STOPPED:
        return AgentOutcome(
            outcome=OUTCOME_STOPPED,
            status=STATUS_STOPPED,
            reason=reason_base,
            tool_call_count=tool_call_count,
            pending_verifications=pending,
            verification_summary=verification_summary,
            exit_reason=exit_reason,
        )

    if exit_reason in {EXIT_TIMEOUT, EXIT_LLM_ERROR}:
        return AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason=reason_base,
            tool_call_count=tool_call_count,
            pending_verifications=pending,
            verification_summary=verification_summary,
            exit_reason=exit_reason,
        )

    if exit_reason == EXIT_EMPTY_LLM:
        if tool_call_count > 0:
            return AgentOutcome(
                outcome=OUTCOME_PARTIAL,
                status=STATUS_COMPLETED,
                reason=f"{reason_base}; partial work preserved",
                tool_call_count=tool_call_count,
                pending_verifications=pending,
                verification_summary=verification_summary,
                exit_reason=exit_reason,
            )
        return AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason=reason_base,
            tool_call_count=tool_call_count,
            pending_verifications=pending,
            verification_summary=verification_summary,
            exit_reason=exit_reason,
        )

    if exit_reason == EXIT_MAX_ITERATIONS:
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason=reason_base,
            tool_call_count=tool_call_count,
            pending_verifications=pending,
            verification_summary=verification_summary,
            exit_reason=exit_reason,
        )

    # final_answer or unknown soft exit
    if pending:
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason="Final answer given but post-change verification is still pending",
            tool_call_count=tool_call_count,
            pending_verifications=pending,
            verification_summary=verification_summary,
            exit_reason=exit_reason or EXIT_FINAL_ANSWER,
        )

    if tools_available and tool_call_count == 0:
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason="Final answer without tool evidence while tools were available",
            tool_call_count=0,
            pending_verifications=pending,
            verification_summary=verification_summary,
            exit_reason=exit_reason or EXIT_FINAL_ANSWER,
        )

    return AgentOutcome(
        outcome=OUTCOME_SUCCESS,
        status=STATUS_COMPLETED,
        reason=reason_base,
        tool_call_count=tool_call_count,
        pending_verifications=pending,
        verification_summary=verification_summary,
        exit_reason=exit_reason or EXIT_FINAL_ANSWER,
    )


def resolve_multi_agent_outcome(
    *,
    stop_requested: bool,
    plan_tasks: list[dict[str, Any]] | None,
    verification_summary: str = "",
    pending_verifications: set[str] | list[str] | tuple[str, ...] | None = None,
) -> AgentOutcome:
    """Map multi-agent plan task states to status + outcome."""
    summary = summarize_plan_tasks(plan_tasks)
    pending_v = tuple(sorted(str(item) for item in (pending_verifications or []) if item))
    aborted = any(
        str((task.get("orchestrator_decision") or {}).get("action") or "").lower() == "abort"
        for task in (plan_tasks or [])
    )
    done = summary["done"]
    failed = summary["failed"]
    skipped = summary["skipped"]
    pending = summary["pending"] + summary["running"]
    tool_proxy_count = sum(len(task.get("iterations") or []) for task in (plan_tasks or []))

    AgentOutcome(
        outcome=OUTCOME_SUCCESS,
        status=STATUS_COMPLETED,
        reason="",
        tool_call_count=tool_proxy_count,
        failed_task_count=failed,
        done_task_count=done,
        skipped_task_count=skipped,
        pending_task_count=pending,
        pending_verifications=pending_v,
        plan_summary=summary,
        verification_summary=verification_summary,
    )

    if stop_requested:
        return AgentOutcome(
            outcome=OUTCOME_STOPPED,
            status=STATUS_STOPPED,
            reason="Multi-agent run stopped by operator",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if aborted:
        return AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason="Orchestrator aborted the multi-agent plan",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if summary["total"] == 0:
        return AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason="Multi-agent plan is empty",
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if pending > 0:
        # Incomplete plan (abort path without decision flag, or interrupted loop)
        if done == 0:
            return AgentOutcome(
                outcome=OUTCOME_FAILED,
                status=STATUS_FAILED,
                reason="Multi-agent plan did not finish; pending tasks remain",
                tool_call_count=tool_proxy_count,
                failed_task_count=failed,
                done_task_count=done,
                skipped_task_count=skipped,
                pending_task_count=pending,
                pending_verifications=pending_v,
                plan_summary=summary,
                verification_summary=verification_summary,
            )
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason="Multi-agent plan partially finished; pending tasks remain",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if failed > 0 and done == 0:
        return AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason=f"All multi-agent tasks failed ({failed})",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if failed > 0 and done > 0:
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason=f"Mixed multi-agent results: {done} done, {failed} failed",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if skipped > 0 and done == 0:
        # timeout / stop-skipped everything
        return AgentOutcome(
            outcome=OUTCOME_FAILED,
            status=STATUS_FAILED,
            reason=f"All multi-agent tasks were skipped ({skipped})",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if skipped > 0 and done > 0:
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason=f"Some multi-agent tasks skipped: {done} done, {skipped} skipped",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    if pending_v:
        return AgentOutcome(
            outcome=OUTCOME_PARTIAL,
            status=STATUS_COMPLETED,
            reason="Tasks completed but post-change verification is still pending",
            tool_call_count=tool_proxy_count,
            failed_task_count=failed,
            done_task_count=done,
            skipped_task_count=skipped,
            pending_task_count=pending,
            pending_verifications=pending_v,
            plan_summary=summary,
            verification_summary=verification_summary,
        )

    return AgentOutcome(
        outcome=OUTCOME_SUCCESS,
        status=STATUS_COMPLETED,
        reason="All multi-agent tasks completed",
        tool_call_count=tool_proxy_count,
        failed_task_count=failed,
        done_task_count=done,
        skipped_task_count=skipped,
        pending_task_count=pending,
        pending_verifications=pending_v,
        plan_summary=summary,
        verification_summary=verification_summary,
    )


def merge_outcome_into_report_payload(
    report_payload: dict[str, Any] | None,
    outcome: AgentOutcome,
) -> dict[str, Any]:
    payload = dict(report_payload or {})
    payload["outcome"] = outcome.outcome
    payload["outcome_reason"] = outcome.reason
    payload["outcome_details"] = outcome.to_payload()
    report = payload.get("report")
    if isinstance(report, dict):
        report = dict(report)
        report["outcome"] = outcome.outcome
        report["outcome_reason"] = outcome.reason
        payload["report"] = report
    return payload


def normalize_on_partial(value: Any) -> str:
    mode = str(value or ON_PARTIAL_ERROR).strip().lower()
    if mode in {ON_PARTIAL_ERROR, ON_PARTIAL_SUCCESS, ON_PARTIAL_ABORT}:
        return mode
    return ON_PARTIAL_ERROR


def map_agent_outcome_to_pipeline_state(
    *,
    outcome: str,
    agent_status: str,
    final_report: str,
    ai_analysis: str,
    agent_run_id: int | None,
    on_partial: str = ON_PARTIAL_ERROR,
    tool_call_count: int = 0,
    failed_task_count: int = 0,
    verification_summary: str = "",
    plan_summary: dict[str, Any] | None = None,
    outcome_reason: str = "",
) -> dict[str, Any]:
    """Translate agent outcome into pipeline node state."""
    on_partial_mode = normalize_on_partial(on_partial)
    resolved_outcome = (outcome or "").strip().lower()
    if not resolved_outcome:
        # Back-compat for older snapshots without outcome field
        if agent_status == STATUS_STOPPED:
            resolved_outcome = OUTCOME_STOPPED
        elif agent_status == STATUS_FAILED:
            resolved_outcome = OUTCOME_FAILED
        elif agent_status == STATUS_COMPLETED:
            resolved_outcome = OUTCOME_SUCCESS
        else:
            resolved_outcome = OUTCOME_FAILED

    error_text = ""
    if resolved_outcome == OUTCOME_SUCCESS:
        pipeline_status = "completed"
    elif resolved_outcome == OUTCOME_STOPPED:
        pipeline_status = "stopped"
        error_text = outcome_reason or ai_analysis or "Agent run stopped"
    elif resolved_outcome == OUTCOME_FAILED:
        pipeline_status = "failed"
        error_text = outcome_reason or ai_analysis or "Agent run failed"
    elif resolved_outcome == OUTCOME_PARTIAL:
        if on_partial_mode == ON_PARTIAL_SUCCESS:
            pipeline_status = "completed"
        elif on_partial_mode == ON_PARTIAL_ABORT:
            pipeline_status = "failed"
            error_text = outcome_reason or "Agent run partially completed (on_partial=abort)"
        else:
            pipeline_status = "failed"
            error_text = outcome_reason or "Agent run partially completed"
    else:
        pipeline_status = "failed"
        error_text = outcome_reason or ai_analysis or f"Unknown agent outcome: {resolved_outcome}"

    state: dict[str, Any] = {
        "status": pipeline_status,
        "outcome": resolved_outcome,
        "outcome_reason": outcome_reason,
        "agent_run_id": agent_run_id,
        "output": final_report or "",
        "error": error_text if pipeline_status != "completed" else "",
        "tool_call_count": tool_call_count,
        "failed_task_count": failed_task_count,
        "verification_summary": verification_summary,
    }
    if plan_summary:
        state["plan_summary"] = plan_summary
    if on_partial_mode and resolved_outcome == OUTCOME_PARTIAL:
        state["on_partial"] = on_partial_mode
    return state


def outcome_from_report_payload(report_payload: dict[str, Any] | None) -> tuple[str, str, dict[str, Any]]:
    payload = report_payload if isinstance(report_payload, dict) else {}
    details = payload.get("outcome_details") if isinstance(payload.get("outcome_details"), dict) else {}
    outcome = str(payload.get("outcome") or details.get("outcome") or "").strip().lower()
    reason = str(payload.get("outcome_reason") or details.get("reason") or "").strip()
    return outcome, reason, details
