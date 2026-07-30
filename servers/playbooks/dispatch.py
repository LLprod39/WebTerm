"""Durable queue and leased execution for prepared playbook runs."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core_ui.managed_secrets import (
    delete_playbook_run_master_password,
    delete_playbook_run_variables,
    set_playbook_run_master_password,
)
from servers.models import PlaybookRun, PlaybookRunDispatch
from servers.services.ansible_docker_runtime import (
    cleanup_claim_runtime_after_commit,
    cleanup_claim_runtime_job,
)
from servers.services.playbook_dispatch_capacity import (
    DEFAULT_PLAYBOOK_GLOBAL_CONCURRENCY,
    DEFAULT_PLAYBOOK_PER_USER_CONCURRENCY,
    lock_playbook_claim_capacity,
    playbook_concurrency_limit,
)
from servers.services.playbook_run_state import (
    TERMINAL_PLAYBOOK_RUN_STATUSES,
    transition_playbook_run,
)

PLAYBOOK_EXECUTION_WORKER_KIND = "playbook_execution"
DEFAULT_PLAYBOOK_LEASE_SECONDS = 180


class PlaybookDispatchError(RuntimeError):
    """The dispatch cannot be executed under its current lease."""


def _lease_delta(lease_seconds: int) -> timedelta:
    return timedelta(seconds=max(int(lease_seconds), 30))


def _dispatch_metadata(run: PlaybookRun, *, has_master_password: bool) -> dict[str, Any]:
    """Build an allowlisted payload; never copy run options wholesale."""
    options = run.options if isinstance(run.options, dict) else {}
    return {
        "engine": str(options.get("engine") or "ansible")[:20],
        "dry_run": bool(options.get("dry_run")),
        "target_count": len(run.target_server_ids or []),
        "revision_id": run.revision_id,
        "validation_id": run.validation_id,
        "binding_profile_id": run.binding_profile_id,
        "has_master_password": bool(has_master_password),
    }


def _targets_still_authorized(run: PlaybookRun) -> bool:
    target_ids = {int(item) for item in (run.target_server_ids or []) if str(item).isdigit()}
    if not target_ids:
        return True
    from servers.services.playbook_runner_support import resolve_target_servers

    authorized = resolve_target_servers(
        run.user,
        server_ids=sorted(target_ids),
        group_ids=[],
    )
    if {server.id for server in authorized} != target_ids:
        return False
    from servers.services.playbooks.target_identity import target_connection_identities_match

    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    return target_connection_identities_match(
        snapshot.get("target_connection_identities"),
        authorized,
    )


def _cleanup_run_execution_secrets(run_id: int) -> None:
    delete_playbook_run_master_password(run_id)
    delete_playbook_run_variables(run_id)


def enqueue_playbook_run_dispatch(
    *,
    run: PlaybookRun,
    master_password: str = "",
    mutation_safe_to_retry: bool = False,
) -> PlaybookRunDispatch:
    """Create one durable dispatch per run and persist its password encrypted."""
    with transaction.atomic():
        locked_run = PlaybookRun.objects.select_for_update().get(pk=run.pk)
        dispatch = PlaybookRunDispatch.objects.filter(run=locked_run).first()
        if dispatch is None:
            if locked_run.status in TERMINAL_PLAYBOOK_RUN_STATUSES:
                raise PlaybookDispatchError("A terminal playbook run cannot be enqueued")
            dispatch = PlaybookRunDispatch.objects.create(
                run=locked_run,
                user_id=locked_run.user_id,
                metadata=_dispatch_metadata(
                    locked_run,
                    has_master_password=bool(master_password),
                ),
                mutation_safe_to_retry=bool(mutation_safe_to_retry),
            )
        elif (
            dispatch.status
            in {
                PlaybookRunDispatch.STATUS_QUEUED,
                PlaybookRunDispatch.STATUS_CLAIMED,
            }
            and master_password
        ):
            metadata = dict(dispatch.metadata or {})
            if not metadata.get("has_master_password"):
                metadata["has_master_password"] = True
                dispatch.metadata = metadata
                dispatch.save(update_fields=["metadata"])

        if master_password and dispatch.status in {
            PlaybookRunDispatch.STATUS_QUEUED,
            PlaybookRunDispatch.STATUS_CLAIMED,
        }:
            set_playbook_run_master_password(locked_run.id, master_password)
        return dispatch


def recover_expired_playbook_dispatches(*, now: datetime | None = None) -> dict[str, int]:
    """Recover expired claims without replaying mutations unless explicitly safe."""
    current = now or timezone.now()
    summary = {"requeued": 0, "interrupted": 0, "canceled": 0}
    expired_ids = list(
        PlaybookRunDispatch.objects.filter(status=PlaybookRunDispatch.STATUS_CLAIMED)
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=current))
        .order_by("lease_expires_at", "id")
        .values_list("id", flat=True)
    )
    for dispatch_id in expired_ids:
        cleanup_run_id: int | None = None
        with transaction.atomic():
            dispatch = (
                PlaybookRunDispatch.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("run")
                .filter(pk=dispatch_id, status=PlaybookRunDispatch.STATUS_CLAIMED)
                .first()
            )
            if dispatch is None:
                continue
            if dispatch.lease_expires_at and dispatch.lease_expires_at > current:
                continue

            run = dispatch.run
            runtime_cleanup = cleanup_claim_runtime_job(
                run.id,
                dispatch.id,
                int(dispatch.attempt_count or 0),
            )
            if run.status in TERMINAL_PLAYBOOK_RUN_STATUSES:
                if run.status == PlaybookRun.STATUS_CANCELLED:
                    dispatch.status = PlaybookRunDispatch.STATUS_CANCELED
                elif run.status == PlaybookRun.STATUS_FAILED:
                    dispatch.status = PlaybookRunDispatch.STATUS_FAILED
                else:
                    dispatch.status = PlaybookRunDispatch.STATUS_COMPLETED
                dispatch.completed_at = current
                dispatch.lease_expires_at = current
                dispatch.save(update_fields=["status", "completed_at", "lease_expires_at"])
                cleanup_run_id = run.id
            elif run.cancel_requested:
                dispatch.status = PlaybookRunDispatch.STATUS_CANCELED
                dispatch.completed_at = current
                dispatch.lease_expires_at = current
                dispatch.error = "Cancellation requested before the worker lease expired."
                dispatch.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
                transition_playbook_run(
                    run.id,
                    PlaybookRun.STATUS_CANCELLED,
                    error_message="Playbook execution was cancelled after its worker lease expired.",
                )
                summary["canceled"] += 1
                cleanup_run_id = run.id
            elif dispatch.mutation_safe_to_retry and runtime_cleanup.safe_to_retry:
                dispatch.status = PlaybookRunDispatch.STATUS_QUEUED
                dispatch.claimed_at = None
                dispatch.heartbeat_at = None
                dispatch.lease_expires_at = None
                dispatch.claimed_by = ""
                dispatch.completed_at = None
                dispatch.error = "Previous worker lease expired; explicitly retry-safe dispatch requeued."
                dispatch.save(
                    update_fields=[
                        "status",
                        "claimed_at",
                        "heartbeat_at",
                        "lease_expires_at",
                        "claimed_by",
                        "completed_at",
                        "error",
                    ]
                )
                PlaybookRun.objects.filter(pk=run.id).update(
                    status=PlaybookRun.STATUS_PENDING,
                    started_at=None,
                    finished_at=None,
                    error_message="",
                )
                summary["requeued"] += 1
            else:
                if dispatch.mutation_safe_to_retry:
                    detail = runtime_cleanup.message or runtime_cleanup.status
                    error = (
                        "Worker lease expired; isolated runtime cleanup could not be confirmed "
                        f"({detail}); automatic retry was suppressed."
                    )
                else:
                    error = "Worker lease expired; mutation is not safe to retry automatically."
                dispatch.status = PlaybookRunDispatch.STATUS_INTERRUPTED
                dispatch.completed_at = current
                dispatch.lease_expires_at = current
                dispatch.error = error
                dispatch.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
                transition_playbook_run(
                    run.id,
                    PlaybookRun.STATUS_FAILED,
                    error_message=error,
                    summary={"interrupted": True, "retry_suppressed": True},
                )
                summary["interrupted"] += 1
                cleanup_run_id = run.id

            if cleanup_run_id is not None:
                transaction.on_commit(lambda run_id=cleanup_run_id: _cleanup_run_execution_secrets(run_id))
    return summary


def claim_next_playbook_dispatch(
    *,
    worker_name: str,
    lease_seconds: int = DEFAULT_PLAYBOOK_LEASE_SECONDS,
    global_concurrency: int | None = None,
    per_user_concurrency: int | None = None,
) -> PlaybookRunDispatch | None:
    """Transactionally claim the oldest queued run under the global DB limit."""
    now = timezone.now()
    recover_expired_playbook_dispatches(now=now)
    limit = playbook_concurrency_limit(
        global_concurrency,
        setting_name="PLAYBOOK_EXECUTION_GLOBAL_CONCURRENCY",
        default=DEFAULT_PLAYBOOK_GLOBAL_CONCURRENCY,
    )
    user_limit = min(
        limit,
        playbook_concurrency_limit(
            per_user_concurrency,
            setting_name="PLAYBOOK_EXECUTION_PER_USER_CONCURRENCY",
            default=DEFAULT_PLAYBOOK_PER_USER_CONCURRENCY,
        ),
    )
    worker = str(worker_name or "default")[:120]
    with transaction.atomic():
        current_claims = PlaybookRunDispatch.objects.filter(
            status=PlaybookRunDispatch.STATUS_CLAIMED,
            lease_expires_at__gt=now,
        )
        claimed_count = current_claims.count()
        if claimed_count >= limit:
            return None

        saturated_user_ids = [
            int(row["user_id"])
            for row in current_claims.values("user_id").annotate(total=Count("id"))
            if int(row["total"]) >= user_limit
        ]

        candidates = (
            PlaybookRunDispatch.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("run", "user")
            .filter(
                status=PlaybookRunDispatch.STATUS_QUEUED,
                run__status=PlaybookRun.STATUS_PENDING,
                run__cancel_requested=False,
            )
            .order_by("queued_at", "id")
        )
        if saturated_user_ids:
            candidates = candidates.exclude(user_id__in=saturated_user_ids)
        dispatch = candidates.first()
        if dispatch is None:
            return None
        if not _targets_still_authorized(dispatch.run):
            error = "Target authorization or connection identity changed after preflight; create a new playbook run."
            dispatch.status = PlaybookRunDispatch.STATUS_FAILED
            dispatch.completed_at = now
            dispatch.lease_expires_at = now
            dispatch.error = error
            dispatch.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
            transition_playbook_run(
                dispatch.run_id,
                PlaybookRun.STATUS_FAILED,
                error_message=error,
                summary={"authorization_or_identity_changed": True},
            )
            transaction.on_commit(lambda run_id=dispatch.run_id: _cleanup_run_execution_secrets(run_id))
            return None

        # Candidate authorization can involve several reads. Keep it outside
        # the short capacity critical section so other workers can validate
        # different skip-locked rows concurrently.
        lock_playbook_claim_capacity()
        current_claims = PlaybookRunDispatch.objects.filter(
            status=PlaybookRunDispatch.STATUS_CLAIMED,
            lease_expires_at__gt=now,
        )
        if current_claims.count() >= limit:
            return None
        if current_claims.filter(user_id=dispatch.user_id).count() >= user_limit:
            return None
        dispatch.status = PlaybookRunDispatch.STATUS_CLAIMED
        dispatch.claimed_at = now
        dispatch.heartbeat_at = now
        dispatch.lease_expires_at = now + _lease_delta(lease_seconds)
        dispatch.claimed_by = worker
        dispatch.attempt_count = int(dispatch.attempt_count or 0) + 1
        dispatch.error = ""
        dispatch.save(
            update_fields=[
                "status",
                "claimed_at",
                "heartbeat_at",
                "lease_expires_at",
                "claimed_by",
                "attempt_count",
                "error",
            ]
        )
        return dispatch


def heartbeat_playbook_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    lease_seconds: int = DEFAULT_PLAYBOOK_LEASE_SECONDS,
    attempt_count: int | None = None,
) -> bool:
    """Extend only the lease owned by this worker."""
    now = timezone.now()
    queryset = PlaybookRunDispatch.objects.filter(
        pk=dispatch_id,
        status=PlaybookRunDispatch.STATUS_CLAIMED,
        claimed_by=str(worker_name or "default")[:120],
    )
    if attempt_count is not None:
        queryset = queryset.filter(attempt_count=int(attempt_count))
    updated = queryset.update(
        heartbeat_at=now,
        lease_expires_at=now + _lease_delta(lease_seconds),
    )
    return bool(updated)


def complete_playbook_dispatch(
    dispatch_id: int,
    *,
    worker_name: str = "",
    attempt_count: int | None = None,
) -> PlaybookRunDispatch | None:
    now = timezone.now()
    with transaction.atomic():
        dispatch = PlaybookRunDispatch.objects.select_for_update().filter(pk=dispatch_id).first()
        if dispatch is None:
            return None
        if dispatch.status in {
            PlaybookRunDispatch.STATUS_CANCELED,
            PlaybookRunDispatch.STATUS_INTERRUPTED,
            PlaybookRunDispatch.STATUS_FAILED,
        }:
            return dispatch
        if worker_name and dispatch.claimed_by and dispatch.claimed_by != str(worker_name)[:120]:
            return dispatch
        if attempt_count is not None and dispatch.attempt_count != int(attempt_count):
            return dispatch
        dispatch.status = PlaybookRunDispatch.STATUS_COMPLETED
        dispatch.completed_at = now
        dispatch.lease_expires_at = now
        dispatch.save(update_fields=["status", "completed_at", "lease_expires_at"])
        return dispatch


def fail_playbook_dispatch(
    dispatch_id: int,
    *,
    error: str,
    worker_name: str = "",
    attempt_count: int | None = None,
) -> PlaybookRunDispatch | None:
    now = timezone.now()
    with transaction.atomic():
        dispatch = PlaybookRunDispatch.objects.select_for_update().filter(pk=dispatch_id).first()
        if dispatch is None:
            return None
        if dispatch.status in {
            PlaybookRunDispatch.STATUS_COMPLETED,
            PlaybookRunDispatch.STATUS_CANCELED,
            PlaybookRunDispatch.STATUS_INTERRUPTED,
        }:
            return dispatch
        if worker_name and dispatch.claimed_by and dispatch.claimed_by != str(worker_name)[:120]:
            return dispatch
        if attempt_count is not None and dispatch.attempt_count != int(attempt_count):
            return dispatch
        dispatch.status = PlaybookRunDispatch.STATUS_FAILED
        dispatch.completed_at = now
        dispatch.lease_expires_at = now
        dispatch.error = str(error)[:4000]
        dispatch.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
        return dispatch


def cancel_playbook_dispatch_for_run(run_id: int, *, reason: str = "user_requested") -> bool:
    """Persist cancellation so queued and active workers observe the same flag."""
    cleanup_now = False
    found = False
    with transaction.atomic():
        dispatch = PlaybookRunDispatch.objects.select_for_update().filter(run_id=run_id).first()
        run = PlaybookRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None:
            return False
        if not run.cancel_requested:
            run.cancel_requested = True
            run.save(update_fields=["cancel_requested"])
        if dispatch is None:
            return False
        found = True
        transaction.on_commit(
            lambda dispatch=dispatch: cleanup_claim_runtime_after_commit(
                dispatch.run_id,
                dispatch.id,
                int(dispatch.attempt_count or 0),
            )
        )
        if dispatch.status == PlaybookRunDispatch.STATUS_QUEUED:
            dispatch.status = PlaybookRunDispatch.STATUS_CANCELED
            dispatch.completed_at = timezone.now()
            dispatch.error = str(reason or "user_requested")[:4000]
            dispatch.save(update_fields=["status", "completed_at", "error"])
            if run.status not in TERMINAL_PLAYBOOK_RUN_STATUSES:
                transition_playbook_run(run.id, PlaybookRun.STATUS_CANCELLED)
            cleanup_now = True
        elif dispatch.status in {
            PlaybookRunDispatch.STATUS_COMPLETED,
            PlaybookRunDispatch.STATUS_FAILED,
            PlaybookRunDispatch.STATUS_CANCELED,
            PlaybookRunDispatch.STATUS_INTERRUPTED,
        }:
            cleanup_now = True
        if cleanup_now:
            transaction.on_commit(lambda: _cleanup_run_execution_secrets(run_id))
    return found


def execute_playbook_dispatch(
    dispatch_id: int,
    *,
    worker_name: str = "default",
    lease_seconds: int = DEFAULT_PLAYBOOK_LEASE_SECONDS,
    shutdown_event: threading.Event | None = None,
) -> None:
    """Facade preserving the public dispatch API after the worker split."""
    from servers.playbooks.worker import execute_playbook_dispatch as execute

    execute(
        dispatch_id,
        worker_name=worker_name,
        lease_seconds=lease_seconds,
        shutdown_event=shutdown_event,
    )


def serialize_playbook_dispatch(dispatch: PlaybookRunDispatch | None) -> dict[str, Any] | None:
    if dispatch is None:
        return None
    return {
        "id": dispatch.id,
        "run_id": dispatch.run_id,
        "status": dispatch.status,
        "queued_at": dispatch.queued_at.isoformat() if dispatch.queued_at else None,
        "claimed_at": dispatch.claimed_at.isoformat() if dispatch.claimed_at else None,
        "heartbeat_at": dispatch.heartbeat_at.isoformat() if dispatch.heartbeat_at else None,
        "lease_expires_at": dispatch.lease_expires_at.isoformat() if dispatch.lease_expires_at else None,
        "completed_at": dispatch.completed_at.isoformat() if dispatch.completed_at else None,
        "claimed_by": dispatch.claimed_by,
        "attempt_count": int(dispatch.attempt_count or 0),
        "error": dispatch.error or "",
        "mutation_safe_to_retry": bool(dispatch.mutation_safe_to_retry),
        "metadata": dispatch.metadata or {},
    }
