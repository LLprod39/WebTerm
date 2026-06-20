from __future__ import annotations

from typing import Any, Protocol

from django.conf import settings
from django.contrib.auth.models import User

ACTIVE_AGENT_RUN_STATUSES = [
    "pending",
    "running",
    "paused",
    "waiting",
    "plan_review",
]

ACTIVE_PIPELINE_RUN_STATUSES = [
    "pending",
    "running",
]

ACTIVE_TERMINAL_CONNECTION_STATUSES = ["connected"]


class AgentRunLimitProvider(Protocol):
    def count_active_runs(self, *, user_id: int | None = None) -> int: ...


class PipelineRunLimitProvider(Protocol):
    def cleanup_stale_runs(self, *, stale_seconds: int) -> int: ...

    def active_runs_queryset(self, *, stale_seconds: int, cleanup_stale: bool = True) -> Any: ...

    def count_active_runs(
        self,
        *,
        stale_seconds: int,
        owner_id: int | None = None,
        cleanup_stale: bool = True,
    ) -> int: ...


class TerminalSessionLimitProvider(Protocol):
    def cleanup_stale_sessions(self, *, stale_seconds: int) -> int: ...

    def active_connections_queryset(self, *, stale_seconds: int) -> Any: ...

    def count_active_connections(self, *, stale_seconds: int, user_id: int | None = None) -> int: ...


_agent_run_limit_provider: AgentRunLimitProvider | None = None
_pipeline_run_limit_provider: PipelineRunLimitProvider | None = None
_terminal_session_limit_provider: TerminalSessionLimitProvider | None = None


def register_agent_run_limit_provider(provider: AgentRunLimitProvider | None) -> None:
    global _agent_run_limit_provider
    _agent_run_limit_provider = provider


def register_pipeline_run_limit_provider(provider: PipelineRunLimitProvider | None) -> None:
    global _pipeline_run_limit_provider
    _pipeline_run_limit_provider = provider


def register_terminal_session_limit_provider(provider: TerminalSessionLimitProvider | None) -> None:
    global _terminal_session_limit_provider
    _terminal_session_limit_provider = provider


def _require_agent_run_limit_provider() -> AgentRunLimitProvider:
    if _agent_run_limit_provider is None:
        raise RuntimeError("Agent run limit provider is not registered")
    return _agent_run_limit_provider


def _require_pipeline_run_limit_provider() -> PipelineRunLimitProvider:
    if _pipeline_run_limit_provider is None:
        raise RuntimeError("Pipeline run limit provider is not registered")
    return _pipeline_run_limit_provider


def _require_terminal_session_limit_provider() -> TerminalSessionLimitProvider:
    if _terminal_session_limit_provider is None:
        raise RuntimeError("Terminal session limit provider is not registered")
    return _terminal_session_limit_provider


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


def _pipeline_run_stale_seconds() -> int:
    return _limit_value("PIPELINE_RUN_STALE_SECONDS")


def cleanup_stale_pipeline_runs() -> int:
    stale_seconds = _pipeline_run_stale_seconds()
    if stale_seconds <= 0:
        return 0
    if _pipeline_run_limit_provider is None:
        return 0
    return _pipeline_run_limit_provider.cleanup_stale_runs(stale_seconds=stale_seconds)


def cleanup_stale_terminal_sessions() -> int:
    stale_seconds = _terminal_session_stale_seconds()
    if stale_seconds <= 0:
        return 0
    if _terminal_session_limit_provider is None:
        return 0
    return _terminal_session_limit_provider.cleanup_stale_sessions(stale_seconds=stale_seconds)


def get_active_terminal_connections_queryset():
    return _require_terminal_session_limit_provider().active_connections_queryset(
        stale_seconds=_terminal_session_stale_seconds(),
    )


def get_active_pipeline_runs_queryset(*, cleanup_stale: bool = True):
    return _require_pipeline_run_limit_provider().active_runs_queryset(
        stale_seconds=_pipeline_run_stale_seconds(),
        cleanup_stale=cleanup_stale,
    )


def get_agent_run_limit_error(user: User | None) -> dict[str, object] | None:
    if user is not None:
        per_user_limit = _limit_value("AGENT_ACTIVE_RUNS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_user = _require_agent_run_limit_provider().count_active_runs(user_id=user.id)
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
        active_global = _require_agent_run_limit_provider().count_active_runs()
        if active_global >= global_limit:
            return _limit_error(
                code="agent_global_limit_reached",
                message=f"Too many active agent runs globally (limit {global_limit})",
                limit=global_limit,
                active=active_global,
                scope="global",
            )

    return None


def get_pipeline_run_limit_error(owner: User | None, *, cleanup_stale: bool = True) -> dict[str, object] | None:
    stale_seconds = _pipeline_run_stale_seconds()
    if cleanup_stale:
        cleanup_stale_pipeline_runs()

    if owner is not None:
        per_user_limit = _limit_value("PIPELINE_ACTIVE_RUNS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_owner = _require_pipeline_run_limit_provider().count_active_runs(
                owner_id=owner.id,
                stale_seconds=stale_seconds,
                cleanup_stale=False,
            )
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
        active_global = _require_pipeline_run_limit_provider().count_active_runs(
            stale_seconds=stale_seconds,
            cleanup_stale=False,
        )
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
    stale_seconds = _terminal_session_stale_seconds()

    if user is not None:
        per_user_limit = _limit_value("SSH_TERMINAL_SESSIONS_PER_USER_LIMIT")
        if per_user_limit:
            active_for_user = _require_terminal_session_limit_provider().count_active_connections(
                user_id=user.id,
                stale_seconds=stale_seconds,
            )
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
        active_global = _require_terminal_session_limit_provider().count_active_connections(
            stale_seconds=stale_seconds,
        )
        if active_global >= global_limit:
            return _limit_error(
                code="terminal_global_limit_reached",
                message=f"Too many active terminal sessions globally (limit {global_limit})",
                limit=global_limit,
                active=active_global,
                scope="global",
            )

    return None
