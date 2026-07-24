"""Controlled PlaybookRun terminal transitions and side effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from loguru import logger

from app.core.redacted_logging import redacted_log_text
from core_ui.activity import log_user_activity
from core_ui.models import UserActivityLog
from servers.models import Playbook, PlaybookRun

TERMINAL_PLAYBOOK_RUN_STATUSES = frozenset(
    {
        PlaybookRun.STATUS_COMPLETED,
        PlaybookRun.STATUS_FAILED,
        PlaybookRun.STATUS_PARTIAL,
        PlaybookRun.STATUS_CANCELLED,
    }
)
TERMINAL_NOTIFICATION_LEASE_SECONDS = 300
MAX_TERMINAL_NOTIFICATION_SWEEP = 500
_NOTIFICATION_STATE_FIELDS = frozenset(
    {
        "terminal_notified_at",
        "terminal_notification_claimed_at",
        "terminal_notification_attempts",
        "terminal_notification_last_error",
    }
)


@dataclass(frozen=True)
class PlaybookRunTransition:
    run: PlaybookRun
    transitioned: bool


@dataclass(frozen=True)
class PlaybookRunNotificationClaim:
    run_id: int
    claimed_at: datetime
    attempt: int


def _notify_operator(run_id: int) -> None:
    from core_ui.services.operator_async import notify_playbook_run_terminal

    notify_playbook_run_terminal(run_id)


def _cleanup_runtime_secrets(run_id: int) -> None:
    from core_ui.managed_secrets import (
        delete_playbook_run_master_password,
        delete_playbook_run_variables,
    )

    delete_playbook_run_master_password(run_id)
    delete_playbook_run_variables(run_id)


def _cleanup_runtime_secrets_safely(run_id: int) -> None:
    try:
        _cleanup_runtime_secrets(run_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Playbook run {} terminal secret cleanup failed: {}",
            run_id,
            redacted_log_text(exc, limit=1000),
        )


def _claim_terminal_notification(
    run_id: int,
    *,
    lease_seconds: int,
) -> PlaybookRunNotificationClaim | None:
    """Claim one pending notification with an atomic attempt-number fence."""
    now = timezone.now()
    stale_before = now - timedelta(seconds=max(1, int(lease_seconds)))
    eligible = PlaybookRun.objects.filter(
        pk=run_id,
        status__in=TERMINAL_PLAYBOOK_RUN_STATUSES,
        terminal_notified_at__isnull=True,
    ).filter(Q(terminal_notification_claimed_at__isnull=True) | Q(terminal_notification_claimed_at__lte=stale_before))
    row = eligible.values("terminal_notification_attempts").first()
    if row is None:
        return None
    previous_attempt = int(row["terminal_notification_attempts"] or 0)
    updated = eligible.filter(terminal_notification_attempts=previous_attempt).update(
        terminal_notification_claimed_at=now,
        terminal_notification_attempts=previous_attempt + 1,
    )
    if not updated:
        return None
    return PlaybookRunNotificationClaim(
        run_id=run_id,
        claimed_at=now,
        attempt=previous_attempt + 1,
    )


def _claim_queryset(claim: PlaybookRunNotificationClaim):
    return PlaybookRun.objects.filter(
        pk=claim.run_id,
        terminal_notified_at__isnull=True,
        terminal_notification_claimed_at=claim.claimed_at,
        terminal_notification_attempts=claim.attempt,
    )


def deliver_playbook_run_terminal_notification(
    run_id: int,
    *,
    lease_seconds: int = TERMINAL_NOTIFICATION_LEASE_SECONDS,
) -> bool:
    """Deliver one terminal notification outside a DB transaction.

    The delivery is at-least-once across a process crash: a crashed claim can
    be reclaimed after its lease, while the attempt number fences stale
    finalizers from marking a newer delivery as complete.
    """
    try:
        claim = _claim_terminal_notification(run_id, lease_seconds=lease_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Playbook run {} notification claim failed: {}",
            run_id,
            redacted_log_text(exc, limit=1000),
        )
        return False
    if claim is None:
        return False

    try:
        _notify_operator(run_id)
    except Exception as exc:  # noqa: BLE001
        error = redacted_log_text(exc, limit=4000)
        try:
            _claim_queryset(claim).update(
                terminal_notification_claimed_at=None,
                terminal_notification_last_error=error,
            )
        except Exception as release_exc:  # noqa: BLE001
            logger.warning(
                "Playbook run {} notification claim release failed: {}",
                run_id,
                redacted_log_text(release_exc, limit=1000),
            )
        logger.warning("Playbook run {} terminal notification failed: {}", run_id, error)
        return False

    try:
        finalized = _claim_queryset(claim).update(
            terminal_notified_at=timezone.now(),
            terminal_notification_claimed_at=None,
            terminal_notification_last_error="",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Playbook run {} notification finalize failed: {}",
            run_id,
            redacted_log_text(exc, limit=1000),
        )
        return False
    return bool(finalized)


def deliver_pending_playbook_run_notifications(
    *,
    limit: int = 100,
    lease_seconds: int = TERMINAL_NOTIFICATION_LEASE_SECONDS,
) -> int:
    """Sweep pending and stale terminal notification claims."""
    bounded_limit = max(1, min(int(limit), MAX_TERMINAL_NOTIFICATION_SWEEP))
    stale_before = timezone.now() - timedelta(seconds=max(1, int(lease_seconds)))
    try:
        run_ids = list(
            PlaybookRun.objects.filter(
                status__in=TERMINAL_PLAYBOOK_RUN_STATUSES,
                terminal_notified_at__isnull=True,
            )
            .filter(
                Q(terminal_notification_claimed_at__isnull=True) | Q(terminal_notification_claimed_at__lte=stale_before)
            )
            .order_by("finished_at", "id")
            .values_list("id", flat=True)[:bounded_limit]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Pending playbook notification sweep failed: {}",
            redacted_log_text(exc, limit=1000),
        )
        return 0
    return sum(deliver_playbook_run_terminal_notification(run_id, lease_seconds=lease_seconds) for run_id in run_ids)


def _schedule_terminal_side_effects(run_id: int, *, notify: bool) -> None:
    # Keep secret cleanup independent from notification delivery and its retry
    # state. Both callbacks are exception-safe and run only after commit.
    transaction.on_commit(lambda run_pk=run_id: _cleanup_runtime_secrets_safely(run_pk))
    if notify:
        transaction.on_commit(lambda run_pk=run_id: deliver_playbook_run_terminal_notification(run_pk))


def _audit_status(status: str) -> str:
    if status == PlaybookRun.STATUS_COMPLETED:
        return UserActivityLog.STATUS_SUCCESS
    if status == PlaybookRun.STATUS_FAILED:
        return UserActivityLog.STATUS_ERROR
    return UserActivityLog.STATUS_INFO


def transition_playbook_run(
    run_id: int,
    status: str,
    **fields: Any,
) -> PlaybookRunTransition:
    """Atomically enter one terminal state and enqueue its notification."""

    if status not in TERMINAL_PLAYBOOK_RUN_STATUSES:
        raise ValueError(f"Not a terminal playbook run status: {status}")
    fields.pop("status", None)
    fields.setdefault("finished_at", timezone.now())

    with transaction.atomic():
        run = PlaybookRun.objects.select_for_update().select_related("playbook", "user").get(pk=run_id)
        if run.status in TERMINAL_PLAYBOOK_RUN_STATUSES:
            should_notify = run.terminal_notified_at is None
            _schedule_terminal_side_effects(run.pk, notify=should_notify)
            return PlaybookRunTransition(run=run, transitioned=False)

        previous_status = run.status
        update_fields = [
            "status",
            "terminal_notified_at",
            "terminal_notification_claimed_at",
            "terminal_notification_last_error",
        ]
        run.status = status
        run.terminal_notified_at = None
        run.terminal_notification_claimed_at = None
        run.terminal_notification_last_error = ""
        for name, value in fields.items():
            try:
                model_field = run._meta.get_field(name)
            except Exception as exc:
                raise ValueError(f"Unknown PlaybookRun transition field: {name}") from exc
            if (
                model_field.primary_key
                or name in {"user", "playbook", "created_at"}
                or name in _NOTIFICATION_STATE_FIELDS
            ):
                raise ValueError(f"PlaybookRun transition cannot update field: {name}")
            setattr(run, name, value)
            update_fields.append(name)
        run.save(update_fields=update_fields)

        if run.playbook_id:
            Playbook.objects.filter(pk=run.playbook_id).update(
                last_run_at=run.finished_at or timezone.now(),
                last_run_status=status,
            )
        snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
        log_user_activity(
            user_id=run.user_id,
            username_snapshot=getattr(run.user, "username", ""),
            category="servers",
            action="playbook_run_terminal",
            status=_audit_status(status),
            description=f"Playbook run #{run.pk} transitioned to {status}",
            entity_type="playbook_run",
            entity_id=run.pk,
            entity_name=str(snapshot.get("name") or "Playbook"),
            metadata={"from_status": previous_status, "to_status": status},
        )
        _schedule_terminal_side_effects(run.pk, notify=True)
        return PlaybookRunTransition(run=run, transitioned=True)
