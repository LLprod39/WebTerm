from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from servers.models import AgentRun, ServerConnection
from studio.models import PipelineRun

ACTIVE_AGENT_RUN_STATUSES = [
    AgentRun.STATUS_PENDING,
    AgentRun.STATUS_RUNNING,
    AgentRun.STATUS_PAUSED,
    AgentRun.STATUS_WAITING,
    AgentRun.STATUS_PLAN_REVIEW,
]

ACTIVE_PIPELINE_RUN_STATUSES = [
    PipelineRun.STATUS_PENDING,
    PipelineRun.STATUS_RUNNING,
]

ACTIVE_TERMINAL_CONNECTION_STATUSES = ["connected"]


def _limit_value(name: str) -> int:
    raw = int(getattr(settings, name, 0) or 0)
    return max(raw, 0)


def _limit_error(*, code: str, message: str, limit: int, active: int, scope: str) -> dict[str, object]:
    return {
        "success": False,
        "error": message,
        "code": code,
        "limit": limit,
        "active": active,
        "scope": scope,
    }


def _terminal_session_stale_seconds() -> int:
    return _limit_value("SSH_TERMINAL_SESSION_STALE_SECONDS")


def cleanup_stale_terminal_sessions() -> int:
    stale_seconds = _terminal_session_stale_seconds()
    if stale_seconds <= 0:
        return 0

    now = timezone.now()
    cutoff = now - timedelta(seconds=stale_seconds)
    return ServerConnection.objects.filter(
        status__in=ACTIVE_TERMINAL_CONNECTION_STATUSES,
        disconnected_at__isnull=True,
        last_seen_at__lt=cutoff,
    ).update(
        status="disconnected",
        disconnected_at=now,
    )


def get_active_terminal_connections_queryset():
    queryset = ServerConnection.objects.filter(
        status__in=ACTIVE_TERMINAL_CONNECTION_STATUSES,
        disconnected_at__isnull=True,
    )
    stale_seconds = _terminal_session_stale_seconds()
    if stale_seconds <= 0:
        return queryset

    cutoff = timezone.now() - timedelta(seconds=stale_seconds)
    return queryset.filter(last_seen_at__gte=cutoff)


def get_agent_run_limit_error(user: User | None) -> dict[str, object] | None:
    if user is not None:
        per_user_limit = _limit_value("AGENT_ACTIVE_RUNS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_user = AgentRun.objects.filter(
                user=user,
                status__in=ACTIVE_AGENT_RUN_STATUSES,
            ).count()
            if active_for_user >= per_user_limit:
                return _limit_error(
                    code="agent_user_limit_reached",
                    message=f"Too many active agent runs for this user (limit {per_user_limit})",
                    limit=per_user_limit,
                    active=active_for_user,
                    scope="user",
                )

    global_limit = _limit_value("AGENT_ACTIVE_RUNS_GLOBAL_LIMIT")
    if global_limit:
        active_global = AgentRun.objects.filter(status__in=ACTIVE_AGENT_RUN_STATUSES).count()
        if active_global >= global_limit:
            return _limit_error(
                code="agent_global_limit_reached",
                message=f"Too many active agent runs globally (limit {global_limit})",
                limit=global_limit,
                active=active_global,
                scope="global",
            )

    return None


def get_pipeline_run_limit_error(owner: User | None) -> dict[str, object] | None:
    if owner is not None:
        per_user_limit = _limit_value("PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_owner = PipelineRun.objects.filter(
                pipeline__owner=owner,
                status__in=ACTIVE_PIPELINE_RUN_STATUSES,
            ).count()
            if active_for_owner >= per_user_limit:
                return _limit_error(
                    code="pipeline_user_limit_reached",
                    message=f"Too many active pipeline runs for this user (limit {per_user_limit})",
                    limit=per_user_limit,
                    active=active_for_owner,
                    scope="user",
                )

    global_limit = _limit_value("PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT")
    if global_limit:
        active_global = PipelineRun.objects.filter(status__in=ACTIVE_PIPELINE_RUN_STATUSES).count()
        if active_global >= global_limit:
            return _limit_error(
                code="pipeline_global_limit_reached",
                message=f"Too many active pipeline runs globally (limit {global_limit})",
                limit=global_limit,
                active=active_global,
                scope="global",
            )

    return None


def get_terminal_session_limit_error(user: User | None) -> dict[str, object] | None:
    cleanup_stale_terminal_sessions()
    active_queryset = get_active_terminal_connections_queryset()

    if user is not None:
        per_user_limit = _limit_value("SSH_TERMINAL_SESSIONS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_user = active_queryset.filter(
                user=user,
            ).count()
            if active_for_user >= per_user_limit:
                return _limit_error(
                    code="terminal_user_limit_reached",
                    message=f"Too many active terminal sessions for this user (limit {per_user_limit})",
                    limit=per_user_limit,
                    active=active_for_user,
                    scope="user",
                )

    global_limit = _limit_value("SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT")
    if global_limit:
        active_global = active_queryset.count()
        if active_global >= global_limit:
            return _limit_error(
                code="terminal_global_limit_reached",
                message=f"Too many active terminal sessions globally (limit {global_limit})",
                limit=global_limit,
                active=active_global,
                scope="global",
            )

    return None
