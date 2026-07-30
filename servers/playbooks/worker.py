"""Foreground execution and heartbeat lifecycle for claimed playbook dispatches."""

from __future__ import annotations

import logging
import threading
from functools import partial
from typing import Any

from django.db import close_old_connections, transaction
from django.utils import timezone

from app.core.redacted_logging import redacted_log_text
from core_ui.managed_secrets import (
    get_playbook_run_master_password,
    get_playbook_run_variables,
)
from servers.models import PlaybookRun, PlaybookRunDispatch
from servers.playbooks.dispatch import (
    DEFAULT_PLAYBOOK_LEASE_SECONDS,
    PLAYBOOK_EXECUTION_WORKER_KIND,
    PlaybookDispatchError,
    _cleanup_run_execution_secrets,
    complete_playbook_dispatch,
    fail_playbook_dispatch,
    heartbeat_playbook_dispatch,
)
from servers.services.playbook_run_state import (
    TERMINAL_PLAYBOOK_RUN_STATUSES,
    transition_playbook_run,
)
from servers.services.playbook_runner import execute_playbook_run
from servers.services.playbook_runner_support import (
    PlaybookRunExecutionFence,
    _persist_run,
    playbook_run_fence_is_owned,
)
from servers.worker_state import heartbeat_background_worker

logger = logging.getLogger(__name__)


def _secret_text_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _secret_text_values(nested)]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _secret_text_values(nested)]
    if value is None:
        return []
    return [str(value)]


def _redacted_error(
    value: object,
    *,
    run_id: int | None = None,
    master_password: str = "",
    secret_values: list[str] | None = None,
) -> str:
    text = redacted_log_text(value, limit=4000)
    candidates: list[str] = [str(master_password or ""), *(secret_values or [])]
    if run_id is not None:
        try:
            variables = get_playbook_run_variables(run_id)
        except Exception:
            variables = {}
        candidates.extend(_secret_text_values(variables))
    for secret in sorted({item for item in candidates if len(item) >= 3}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text[:4000]


def _heartbeat_loop(
    stop: threading.Event,
    lost_lease: threading.Event,
    *,
    dispatch_id: int,
    run_id: int,
    worker_name: str,
    attempt_count: int,
    lease_seconds: int,
) -> None:
    close_old_connections()
    interval = max(5, min(int(max(lease_seconds, 30) // 3), 60))
    try:
        # The claim itself writes a fresh lease. Waiting before the first
        # heartbeat avoids racing an immediate terminal transition/cleanup
        # (notably on SQLite) without shortening the effective lease.
        while not stop.wait(interval):
            try:
                owned = heartbeat_playbook_dispatch(
                    dispatch_id,
                    worker_name=worker_name,
                    attempt_count=attempt_count,
                    lease_seconds=lease_seconds,
                )
                if not owned:
                    lost_lease.set()
                    break
                heartbeat_background_worker(
                    PLAYBOOK_EXECUTION_WORKER_KIND,
                    worker_key=worker_name,
                    lease_seconds=lease_seconds,
                    summary={"active_dispatch_id": dispatch_id, "run_id": run_id},
                )
            except Exception:
                logger.warning("Playbook dispatch heartbeat failed for dispatch %s", dispatch_id, exc_info=True)
                close_old_connections()
    finally:
        close_old_connections()


def _finish_canceled_dispatch(
    fence: PlaybookRunExecutionFence,
    run_id: int,
    *,
    reason: str,
) -> bool:
    now = timezone.now()
    with transaction.atomic():
        dispatch = (
            PlaybookRunDispatch.objects.select_for_update()
            .filter(
                pk=fence.dispatch_id,
                status=PlaybookRunDispatch.STATUS_CLAIMED,
                claimed_by=fence.claimed_by,
                attempt_count=fence.attempt_count,
                lease_expires_at__gt=now,
            )
            .first()
        )
        if dispatch is None:
            return False
        run = PlaybookRun.objects.filter(pk=run_id).first()
        if run is not None and run.status not in TERMINAL_PLAYBOOK_RUN_STATUSES:
            transition_playbook_run(run_id, PlaybookRun.STATUS_CANCELLED)
        dispatch.status = PlaybookRunDispatch.STATUS_CANCELED
        dispatch.completed_at = now
        dispatch.lease_expires_at = now
        dispatch.error = reason[:4000]
        dispatch.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
        return True


def _playbook_claim_is_owned(
    *,
    fence: PlaybookRunExecutionFence,
    shutdown_event: threading.Event | None,
    lost_lease: threading.Event,
    dispatch_id: int,
) -> bool:
    if shutdown_event is not None and shutdown_event.is_set():
        lost_lease.set()
        return False
    if lost_lease.is_set():
        return False
    try:
        owned = playbook_run_fence_is_owned(fence)
    except Exception:
        logger.warning("Unable to verify playbook dispatch lease %s", dispatch_id, exc_info=True)
        owned = False
    if not owned:
        lost_lease.set()
    return owned


def execute_playbook_dispatch(
    dispatch_id: int,
    *,
    worker_name: str = "default",
    lease_seconds: int = DEFAULT_PLAYBOOK_LEASE_SECONDS,
    shutdown_event: threading.Event | None = None,
) -> None:
    """Execute one claimed row in the worker process and finalize it once."""
    close_old_connections()
    worker = str(worker_name or "default")[:120]
    dispatch = PlaybookRunDispatch.objects.select_related("run").filter(pk=dispatch_id).first()
    if dispatch is None:
        raise PlaybookDispatchError(f"Playbook dispatch {dispatch_id} does not exist")
    if dispatch.status != PlaybookRunDispatch.STATUS_CLAIMED or dispatch.claimed_by != worker:
        raise PlaybookDispatchError(f"Playbook dispatch {dispatch_id} is not claimed by {worker}")
    if dispatch.lease_expires_at is None or dispatch.lease_expires_at <= timezone.now():
        raise PlaybookDispatchError(f"Playbook dispatch {dispatch_id} lease has expired")
    run_id = int(dispatch.run_id)
    fence = PlaybookRunExecutionFence(
        dispatch_id=dispatch.id,
        claimed_by=worker,
        attempt_count=int(dispatch.attempt_count),
    )
    if dispatch.run.cancel_requested:
        if _finish_canceled_dispatch(fence, run_id, reason="Cancellation observed before execution."):
            _cleanup_run_execution_secrets(run_id)
        return

    master_password = get_playbook_run_master_password(run_id)
    runtime_secret_values = _secret_text_values(get_playbook_run_variables(run_id))
    stop_heartbeat = threading.Event()
    lost_lease = threading.Event()

    owns_claim = partial(
        _playbook_claim_is_owned,
        fence=fence,
        shutdown_event=shutdown_event,
        lost_lease=lost_lease,
        dispatch_id=dispatch.id,
    )

    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        kwargs={
            "stop": stop_heartbeat,
            "lost_lease": lost_lease,
            "dispatch_id": dispatch.id,
            "run_id": run_id,
            "worker_name": worker,
            "attempt_count": fence.attempt_count,
            "lease_seconds": lease_seconds,
        },
        name=f"playbook-heartbeat-{dispatch.id}",
        daemon=True,
    )
    heartbeat_thread.start()
    finalized_by_attempt = False
    try:
        execute_playbook_run(
            run_id,
            master_password=master_password,
            execution_fence=fence,
            lease_check=owns_claim,
        )
        if not owns_claim():
            logger.warning("Playbook dispatch %s lost its lease; stale worker stopped", dispatch.id)
            return
        run = PlaybookRun.objects.get(pk=run_id)
        if run.status not in TERMINAL_PLAYBOOK_RUN_STATUSES:
            if run.cancel_requested:
                persisted = _persist_run(
                    run_id,
                    execution_fence=fence,
                    status=PlaybookRun.STATUS_CANCELLED,
                )
            else:
                persisted = _persist_run(
                    run_id,
                    execution_fence=fence,
                    status=PlaybookRun.STATUS_FAILED,
                    error_message="Playbook worker returned without a terminal run state.",
                )
            if not persisted:
                lost_lease.set()
                return
            run.refresh_from_db()

        if run.status == PlaybookRun.STATUS_CANCELLED:
            finalized_by_attempt = _finish_canceled_dispatch(fence, run_id, reason="Execution cancelled.")
        elif run.status == PlaybookRun.STATUS_FAILED:
            finalized = fail_playbook_dispatch(
                dispatch.id,
                error=_redacted_error(
                    run.error_message or "Playbook execution failed",
                    run_id=run_id,
                    master_password=master_password,
                    secret_values=runtime_secret_values,
                ),
                worker_name=worker,
                attempt_count=fence.attempt_count,
            )
            finalized_by_attempt = bool(finalized is not None and finalized.status == PlaybookRunDispatch.STATUS_FAILED)
        else:
            finalized = complete_playbook_dispatch(
                dispatch.id,
                worker_name=worker,
                attempt_count=fence.attempt_count,
            )
            finalized_by_attempt = bool(
                finalized is not None and finalized.status == PlaybookRunDispatch.STATUS_COMPLETED
            )
    except Exception as exc:
        safe_error = _redacted_error(
            exc,
            run_id=run_id,
            master_password=master_password,
            secret_values=runtime_secret_values,
        )
        if not owns_claim():
            logger.warning("Ignoring stale worker failure for playbook dispatch %s", dispatch.id)
            return
        run = PlaybookRun.objects.filter(pk=run_id).first()
        if run is not None and run.status not in TERMINAL_PLAYBOOK_RUN_STATUSES:
            if run.cancel_requested:
                finalized_by_attempt = _finish_canceled_dispatch(fence, run_id, reason="Execution cancelled.")
            else:
                persisted = _persist_run(
                    run_id,
                    execution_fence=fence,
                    status=PlaybookRun.STATUS_FAILED,
                    error_message=safe_error,
                )
                if persisted:
                    finalized = fail_playbook_dispatch(
                        dispatch.id,
                        error=safe_error,
                        worker_name=worker,
                        attempt_count=fence.attempt_count,
                    )
                    finalized_by_attempt = bool(
                        finalized is not None and finalized.status == PlaybookRunDispatch.STATUS_FAILED
                    )
        else:
            finalized = fail_playbook_dispatch(
                dispatch.id,
                error=safe_error,
                worker_name=worker,
                attempt_count=fence.attempt_count,
            )
            finalized_by_attempt = bool(finalized is not None and finalized.status == PlaybookRunDispatch.STATUS_FAILED)
        raise
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=5)
        if finalized_by_attempt:
            _cleanup_run_execution_secrets(run_id)
        close_old_connections()
