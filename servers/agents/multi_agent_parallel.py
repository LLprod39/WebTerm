"""Pure helpers: which multi-agent plan tasks may run concurrently.

Only **read-only** independent tasks may batch. Mutating roles and any task
that fails the read-only heuristic stay sequential. No full DAG solver —
tasks are batched as a consecutive prefix of pending read-only work at the
execution frontier.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

# Roles that primarily inspect / verify without mutating production state.
READ_ONLY_ROLES: frozenset[str] = frozenset(
    {
        "infra_scout",
        "log_investigator",
        "security_patrol",
        "post_change_verifier",
        "watcher_daemon",
    }
)

# Roles that typically mutate or coordinate risky changes.
MUTATING_ROLES: frozenset[str] = frozenset(
    {
        "deploy_operator",
        "incident_commander",
    }
)

_PENDING_STATUSES = frozenset({"pending", ""})
_SKIP_STATUSES = frozenset({"done", "skipped"})


def task_is_read_only(task: dict[str, Any] | None) -> bool:
    """Return True when a task is safe to run beside other read-only tasks.

    Default is **False** (sequential) for custom/unknown roles so ordinary
    plans without role metadata stay single-file. Parallel only when the
    role is an explicit inspect/verify role or permission_mode is PLAN
    without mutate signals.
    """
    if not isinstance(task, dict):
        return False
    role = str(task.get("role") or "").strip().lower()
    permission = str(task.get("permission_mode") or "").strip().upper()
    if role in MUTATING_ROLES:
        return False
    if permission in {"AUTO_GUARDED", "AUTONOMOUS", "ASSISTED"}:
        # Elevated write-capable modes — keep sequential.
        return False
    # Name/description mutate heuristic (shared with plan verify gate).
    try:
        from servers.services.agent_complexity import plan_mentions_mutation

        if plan_mentions_mutation([task]):
            return False
    except Exception as exc:  # noqa: BLE001 — keep scheduler pure-fail-closed for tests
        logger.warning("multi-agent mutation classifier unavailable; forcing sequential execution: {}", exc)
    if role in READ_ONLY_ROLES:
        return True
    # Explicit PLAN mode on non-mutating custom work may inspect in parallel.
    return bool(permission == "PLAN" and role in {"custom", ""})


def _is_pending(task: dict[str, Any]) -> bool:
    status = str(task.get("status") or "pending").strip().lower()
    return status in _PENDING_STATUSES


def _is_skippable(task: dict[str, Any]) -> bool:
    status = str(task.get("status") or "").strip().lower()
    return status in _SKIP_STATUSES


def select_next_execution_batch(
    plan_tasks: list[dict[str, Any]] | None,
    *,
    skip_completed: bool = True,
    max_parallel: int = 4,
) -> list[dict[str, Any]]:
    """Select the next batch of tasks to execute.

    Returns:
      - multiple read-only pending tasks (size ≥ 2) when a consecutive
        frontier of independent inspect-only work is available;
      - a single-task list for sequential execution otherwise;
      - empty list when nothing remains to run.

    Mutating pending tasks never join a multi-task batch. A mutating task
    that is first at the frontier is returned alone (sequential).
    """
    if not plan_tasks:
        return []

    cap = max(1, int(max_parallel or 1))
    batch: list[dict[str, Any]] = []

    for task in plan_tasks:
        if skip_completed and _is_skippable(task):
            continue
        if not _is_pending(task):
            # Skip non-pending (failed/running/etc.) and keep scanning so a
            # later pending task is still scheduled after an earlier failure
            # that was already handled (ask_user / skip).
            continue

        if not task_is_read_only(task):
            if batch:
                # Stop before mutate; run the collected read-only batch first.
                return batch[:cap]
            return [task]

        batch.append(task)
        if len(batch) >= cap:
            break

    return batch[:cap] if batch else []


def can_run_parallel(batch: list[dict[str, Any]] | None) -> bool:
    """True when the batch should use concurrent gather (size ≥ 2, all read-only)."""
    if not batch or len(batch) < 2:
        return False
    return all(task_is_read_only(task) for task in batch)
