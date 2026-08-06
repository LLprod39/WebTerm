from __future__ import annotations

import os
import socket
from datetime import timedelta
from typing import Any

from django.apps import apps
from django.db import transaction
from django.db.models import Q
from django.utils import timezone


def _worker_state_model():
    return apps.get_model("servers", "BackgroundWorkerState")


def _normalize_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[str(key)] = value
        elif isinstance(value, dict):
            normalized[str(key)] = _normalize_summary(value)
        elif isinstance(value, list):
            normalized[str(key)] = value[:20]
        else:
            normalized[str(key)] = str(value)
    return normalized


def claim_background_worker(
    worker_kind: str,
    *,
    worker_key: str = "default",
    command: str = "",
    lease_seconds: int = 180,
):
    model = _worker_state_model()
    now = timezone.now()
    hostname = socket.gethostname()
    pid = int(os.getpid())
    with transaction.atomic():
        state, _created = model.objects.select_for_update().get_or_create(
            worker_kind=worker_kind,
            worker_key=worker_key,
        )
        lease_valid = bool(state.lease_expires_at and state.lease_expires_at > now)
        same_process = state.hostname == hostname and int(state.pid or 0) == pid
        claimed_by_other = lease_valid and state.status == model.STATUS_RUNNING and not same_process
        if claimed_by_other:
            return None

        state.status = model.STATUS_RUNNING
        state.hostname = hostname
        state.pid = pid
        state.command = command[:255]
        state.heartbeat_at = now
        state.lease_expires_at = now + timedelta(seconds=max(int(lease_seconds), 30))
        state.last_started_at = now
        state.last_error = ""
        state.save(
            update_fields=[
                "status",
                "hostname",
                "pid",
                "command",
                "heartbeat_at",
                "lease_expires_at",
                "last_started_at",
                "last_error",
                "updated_at",
            ]
        )
        return state


def heartbeat_background_worker(
    worker_kind: str,
    *,
    worker_key: str = "default",
    lease_seconds: int = 180,
    summary: dict[str, Any] | None = None,
    cycle_started: bool = False,
    cycle_finished: bool = False,
):
    model = _worker_state_model()
    now = timezone.now()
    state, _created = model.objects.get_or_create(worker_kind=worker_kind, worker_key=worker_key)
    state.status = model.STATUS_RUNNING
    state.hostname = socket.gethostname()
    state.pid = int(os.getpid())
    state.heartbeat_at = now
    state.lease_expires_at = now + timedelta(seconds=max(int(lease_seconds), 30))
    if cycle_started:
        state.last_cycle_started_at = now
    if cycle_finished:
        state.last_cycle_finished_at = now
    if summary:
        state.last_summary = _normalize_summary(summary)
    state.save(
        update_fields=[
            "status",
            "hostname",
            "pid",
            "heartbeat_at",
            "lease_expires_at",
            "last_cycle_started_at",
            "last_cycle_finished_at",
            "last_summary",
            "updated_at",
        ]
    )
    return state


def stop_background_worker(
    worker_kind: str,
    *,
    worker_key: str = "default",
    summary: dict[str, Any] | None = None,
    error: str = "",
):
    model = _worker_state_model()
    now = timezone.now()
    state, _created = model.objects.get_or_create(worker_kind=worker_kind, worker_key=worker_key)
    state.status = model.STATUS_ERROR if error else model.STATUS_IDLE
    state.hostname = socket.gethostname()
    state.pid = int(os.getpid())
    state.heartbeat_at = now
    state.lease_expires_at = now
    state.last_stopped_at = now
    if summary:
        state.last_summary = _normalize_summary(summary)
    if error:
        state.last_error = str(error)[:4000]
    state.save(
        update_fields=[
            "status",
            "hostname",
            "pid",
            "heartbeat_at",
            "lease_expires_at",
            "last_stopped_at",
            "last_summary",
            "last_error",
            "updated_at",
        ]
    )
    return state


def cleanup_stale_background_workers(worker_kind: str | None = None) -> int:
    model = _worker_state_model()
    now = timezone.now()
    queryset = model.objects.filter(status=model.STATUS_RUNNING).filter(
        Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now)
    )
    if worker_kind:
        queryset = queryset.filter(worker_kind=worker_kind)

    count = 0
    for state in queryset:
        state.status = model.STATUS_STOPPED
        state.lease_expires_at = state.lease_expires_at or now
        state.last_stopped_at = now
        if not state.last_error:
            state.last_error = "Worker lease expired before clean shutdown."
        state.save(update_fields=["status", "lease_expires_at", "last_stopped_at", "last_error", "updated_at"])
        count += 1
    return count


def _serialize_background_worker_state(worker_kind: str, worker_key: str, state: Any | None) -> dict[str, Any]:
    model = _worker_state_model()
    if state is None:
        return {
            "worker_kind": worker_kind,
            "worker_key": worker_key,
            "status": "missing",
            "is_stale": True,
            "hostname": "",
            "pid": None,
            "heartbeat_at": None,
            "lease_expires_at": None,
            "last_started_at": None,
            "last_stopped_at": None,
            "last_cycle_started_at": None,
            "last_cycle_finished_at": None,
            "last_summary": {},
            "last_error": "",
        }

    now = timezone.now()
    lease_expires_at = state.lease_expires_at
    is_stale = bool(state.status == model.STATUS_RUNNING and (lease_expires_at is None or lease_expires_at <= now))
    return {
        "worker_kind": state.worker_kind,
        "worker_key": state.worker_key,
        "status": state.status,
        "is_stale": is_stale,
        "hostname": state.hostname,
        "pid": state.pid,
        "command": state.command,
        "heartbeat_at": state.heartbeat_at.isoformat() if state.heartbeat_at else None,
        "lease_expires_at": lease_expires_at.isoformat() if lease_expires_at else None,
        "last_started_at": state.last_started_at.isoformat() if state.last_started_at else None,
        "last_stopped_at": state.last_stopped_at.isoformat() if state.last_stopped_at else None,
        "last_cycle_started_at": state.last_cycle_started_at.isoformat() if state.last_cycle_started_at else None,
        "last_cycle_finished_at": state.last_cycle_finished_at.isoformat() if state.last_cycle_finished_at else None,
        "last_summary": state.last_summary or {},
        "last_error": state.last_error or "",
    }


def serialize_background_worker_state(worker_kind: str, *, worker_key: str = "default") -> dict[str, Any]:
    model = _worker_state_model()
    state = model.objects.filter(worker_kind=worker_kind, worker_key=worker_key).first()
    return _serialize_background_worker_state(worker_kind, worker_key, state)


def serialize_background_worker_kind_state(worker_kind: str) -> dict[str, Any]:
    """Return the best available replica state for a worker kind."""

    model = _worker_state_model()
    now = timezone.now()
    states = list(model.objects.filter(worker_kind=worker_kind).order_by("-updated_at", "worker_key"))
    healthy_states = [
        item
        for item in states
        if item.status == model.STATUS_RUNNING and item.lease_expires_at is not None and item.lease_expires_at > now
    ]
    state = next(
        (item for item in healthy_states),
        states[0] if states else None,
    )
    payload = _serialize_background_worker_state(worker_kind, "*", state)
    payload["replica_count"] = len(states)
    payload["healthy_replica_count"] = len(healthy_states)
    payload["healthy_worker_keys"] = [item.worker_key for item in healthy_states]
    return payload
