"""Django-backed route resolution, invocation pinning, and fenced leases."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from app.ai_runtime import (
    LLMExecutionContext,
    ProviderBinding,
    ProviderRouteUnavailableError,
    ProviderRuntimeError,
    ProviderTarget,
    resolve_provider_route,
)
from core_ui.models.ai_providers import (
    AIProviderConnection,
    AIProviderInvocation,
    AIProviderLease,
    AIProviderPool,
    AIProviderPreference,
)
from core_ui.services.ai_provider_access import can_use_binding, can_use_connection


def binding_from_preference(preference: AIProviderPreference | None) -> ProviderBinding | None:
    if preference is None:
        return None
    return ProviderBinding(
        target_id=preference.target_id,
        connection_id=preference.connection_id,
        pool_id=preference.pool_id,
        model_id=preference.model_id or None,
        reasoning_effort=preference.reasoning_effort or None,
    )


def resolve_execution_context(
    context: LLMExecutionContext,
    *,
    explicit_binding: ProviderBinding | None = None,
    stored_binding: ProviderBinding | None = None,
    platform_default: ProviderBinding | None = None,
    allow_user_preference: bool = True,
) -> LLMExecutionContext:
    """Resolve a binding, optionally skipping personal defaults on centrally routed surfaces."""
    user_default = _user_preference(context) if allow_user_preference else None
    workspace_default = _workspace_preference(context)
    route = resolve_provider_route(
        explicit=explicit_binding or context.binding,
        stored=stored_binding,
        user_default=binding_from_preference(user_default),
        workspace_default=binding_from_preference(workspace_default) or platform_default,
        can_use=lambda binding: can_use_binding(
            binding,
            user_id=context.actor_user_id,
            project_id=context.project_id,
            mode=context.mode,
        ).as_route_decision(),
    )
    return context.with_binding(route.binding)


def _user_preference(context: LLMExecutionContext) -> AIProviderPreference | None:
    if context.actor_user_id is None:
        return None
    preferences = AIProviderPreference.objects.filter(
        user_id=context.actor_user_id,
        purpose=_preference_purpose(context),
    )
    if context.project_id is not None:
        project_preference = preferences.filter(project_id=context.project_id).first()
        if project_preference is not None:
            return project_preference
    return preferences.filter(project__isnull=True).first()


def _workspace_preference(context: LLMExecutionContext) -> AIProviderPreference | None:
    if context.project_id is None:
        return None
    return AIProviderPreference.objects.filter(
        user__isnull=True,
        project_id=context.project_id,
        purpose=_preference_purpose(context),
    ).first()


def _preference_purpose(context: LLMExecutionContext) -> str:
    if context.purpose in {item[0] for item in AIProviderPreference.PURPOSE_CHOICES}:
        return context.purpose
    if context.source_kind in {"chat_session", "pipeline_assistant"}:
        return AIProviderPreference.PURPOSE_ASSISTANT
    if context.source_kind in {"agent_run", "server_agent", "pipeline_run", "pipeline"}:
        return AIProviderPreference.PURPOSE_AGENTS
    if context.source_kind == "terminal_ai_state" or context.purpose.startswith("terminal_"):
        return AIProviderPreference.PURPOSE_TERMINAL
    return AIProviderPreference.PURPOSE_INTERNAL


def _idempotency_scope(context: LLMExecutionContext) -> str:
    if not context.idempotency_key:
        return ""
    canonical = json.dumps(
        {
            "actor_user_id": context.actor_user_id,
            "project_id": context.project_id,
            "source_kind": context.source_kind,
            "source_id": context.source_id,
            "purpose": context.purpose,
            "idempotency_key": context.idempotency_key,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@transaction.atomic
def create_invocation_with_lease(
    context: LLMExecutionContext,
    *,
    owner_id: str,
    lease_seconds: int = 120,
) -> tuple[AIProviderInvocation, AIProviderLease | None]:
    """Create an invocation, pin a pool member, and reserve its slot atomically."""
    if context.binding is None:
        raise ProviderRouteUnavailableError("Execution context has no resolved provider binding")

    idempotency_scope = _idempotency_scope(context)
    if idempotency_scope:
        existing = AIProviderInvocation.objects.select_for_update().filter(idempotency_scope=idempotency_scope).first()
        if existing is not None:
            if existing.status in {
                AIProviderInvocation.STATUS_SUCCEEDED,
                AIProviderInvocation.STATUS_FAILED,
                AIProviderInvocation.STATUS_CANCELLED,
            }:
                return existing, None
            if existing.connection_id is None:
                return existing, None
            connection = AIProviderConnection.objects.select_for_update().get(pk=existing.connection_id)
            _expire_stale_leases(connection)
            active = existing.leases.filter(status=AIProviderLease.STATUS_ACTIVE).first()
            if active is not None:
                return existing, active
            existing.status = AIProviderInvocation.STATUS_QUEUED
            existing.save(update_fields=["status"])
            return existing, _acquire_locked_connection_lease(
                existing,
                connection,
                owner_id=owner_id,
                lease_seconds=lease_seconds,
            )

    binding = context.binding
    connection: AIProviderConnection | None = None
    pool: AIProviderPool | None = None
    lease: AIProviderLease | None = None

    if binding.connection_id is not None:
        connection = AIProviderConnection.objects.select_for_update().filter(pk=binding.connection_id).first()
        if connection is None:
            raise ProviderRouteUnavailableError("Selected provider connection does not exist")
        _require_connection_access(connection, context)
    elif binding.pool_id is not None:
        pool = AIProviderPool.objects.select_for_update().filter(pk=binding.pool_id, enabled=True).first()
        if pool is None or pool.target_id != binding.target_id:
            raise ProviderRouteUnavailableError("Selected provider pool is unavailable")
        connection = _select_pool_connection(pool, context)

    invocation = AIProviderInvocation.objects.create(
        user_id=context.actor_user_id,
        project_id=context.project_id,
        connection=connection,
        pool=pool,
        target_id=binding.target_id,
        purpose=context.purpose,
        source_kind=context.source_kind,
        source_id=context.source_id,
        mode=context.mode.value,
        binding_snapshot={
            **binding.to_dict(),
            "selected_connection_id": connection.pk if connection is not None else None,
        },
        idempotency_key=context.idempotency_key,
        idempotency_scope=idempotency_scope,
    )

    if connection is not None:
        lease = _acquire_locked_connection_lease(
            invocation,
            connection,
            owner_id=owner_id,
            lease_seconds=lease_seconds,
        )
    return invocation, lease


def _select_pool_connection(pool: AIProviderPool, context: LLMExecutionContext) -> AIProviderConnection:
    memberships = {
        member.connection_id: member.weight for member in pool.members.filter(enabled=True).order_by("connection_id")
    }
    durable_assignments = {
        row["connection_id"]: int(row["count"])
        for row in pool.invocations.values("connection_id").annotate(count=Count("id"))
        if row["connection_id"] is not None
    }
    candidates: list[tuple[float, float, int, AIProviderConnection]] = []
    for connection in (
        AIProviderConnection.objects.select_for_update()
        .filter(
            pk__in=memberships,
            scope=AIProviderConnection.SCOPE_WORKSPACE,
            target_id=pool.target_id,
            enabled=True,
            status=AIProviderConnection.STATUS_CONNECTED,
        )
        .order_by("pk")
    ):
        if not can_use_connection(
            connection,
            user_id=context.actor_user_id,
            project_id=context.project_id,
            mode=context.mode,
        ).allowed:
            continue
        if not _connection_is_route_healthy(connection):
            continue
        _expire_stale_leases(connection)
        active_slots = set(
            connection.leases.filter(status=AIProviderLease.STATUS_ACTIVE).values_list("slot", flat=True)
        )
        if any(slot not in active_slots for slot in range(1, connection.concurrency_limit + 1)):
            weight = max(1, int(memberships[connection.pk]))
            # Durable weighted debt prevents the all-idle tie from selecting the
            # lowest primary key forever. Active load remains a second signal.
            debt = (durable_assignments.get(connection.pk, 0) + len(active_slots)) / weight
            load = len(active_slots) / max(1, connection.concurrency_limit)
            candidates.append((debt, load, connection.pk, connection))
    if candidates:
        return min(candidates, key=lambda item: (item[0], item[1], item[2]))[3]
    raise ProviderRuntimeError(
        "provider_capacity_unavailable",
        "Provider pool has no accessible free connection slot",
        retryable=True,
        details={"pool_id": pool.pk, "target_id": pool.target_id},
    )


def _connection_is_route_healthy(connection: AIProviderConnection) -> bool:
    if connection.last_error_code in {
        "provider_auth_required",
        "provider_quota_exceeded",
        "provider_limit_reached",
        "provider_credential_cleanup_pending",
    }:
        return False
    health = connection.health if isinstance(connection.health, dict) else {}
    limits = connection.limits if isinstance(connection.limits, dict) else {}
    if health.get("healthy") is False or health.get("available") is False:
        return False
    if str(health.get("status") or "").strip().lower() in {
        "down",
        "error",
        "failed",
        "offline",
        "unhealthy",
    }:
        return False
    for payload in (health, limits):
        if payload.get("quota_exhausted") is True or payload.get("exhausted") is True:
            return False
        for key in ("quota_remaining", "remaining", "remaining_requests"):
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and value <= 0:
                return False
    return True


def _require_connection_access(connection: AIProviderConnection, context: LLMExecutionContext) -> None:
    if connection.target_id != context.binding.target_id:
        raise ProviderRouteUnavailableError("Connection target does not match resolved binding")
    decision = can_use_connection(
        connection,
        user_id=context.actor_user_id,
        project_id=context.project_id,
        mode=context.mode,
    )
    if not decision.allowed:
        raise ProviderRouteUnavailableError(
            "Selected provider connection is unavailable",
            details={"connection_id": connection.pk, "reason": decision.reason},
        )


def _expire_stale_leases(connection: AIProviderConnection) -> None:
    now = timezone.now()
    connection.leases.filter(status=AIProviderLease.STATUS_ACTIVE, expires_at__lte=now).update(
        status=AIProviderLease.STATUS_EXPIRED,
        released_at=now,
    )


def _acquire_locked_connection_lease(
    invocation: AIProviderInvocation,
    connection: AIProviderConnection,
    *,
    owner_id: str,
    lease_seconds: int,
) -> AIProviderLease:
    _expire_stale_leases(connection)
    active_slots = set(connection.leases.filter(status=AIProviderLease.STATUS_ACTIVE).values_list("slot", flat=True))
    slot = next(
        (candidate for candidate in range(1, connection.concurrency_limit + 1) if candidate not in active_slots),
        None,
    )
    if slot is None:
        raise ProviderRuntimeError(
            "provider_capacity_unavailable",
            "Selected provider connection has no free execution slot",
            retryable=True,
            details={"connection_id": connection.pk},
        )
    max_fencing_token = connection.leases.aggregate(value=Max("fencing_token"))["value"] or 0
    lease = AIProviderLease.objects.create(
        invocation=invocation,
        connection=connection,
        slot=slot,
        fencing_token=max_fencing_token + 1,
        owner_id=owner_id,
        expires_at=timezone.now() + timedelta(seconds=max(1, lease_seconds)),
    )
    if invocation.status != AIProviderInvocation.STATUS_LEASED:
        invocation.status = AIProviderInvocation.STATUS_LEASED
        invocation.save(update_fields=["status"])
    return lease


@transaction.atomic
def heartbeat_provider_lease(
    lease_token: str,
    *,
    owner_id: str,
    lease_seconds: int = 120,
) -> AIProviderLease:
    lease = AIProviderLease.objects.select_for_update().filter(lease_token=lease_token).first()
    if lease is None or lease.owner_id != owner_id:
        raise ProviderRuntimeError("provider_lease_lost", "Provider lease is not owned by this runner")
    now = timezone.now()
    if lease.status != AIProviderLease.STATUS_ACTIVE or lease.expires_at <= now:
        if lease.status == AIProviderLease.STATUS_ACTIVE:
            lease.status = AIProviderLease.STATUS_EXPIRED
            lease.released_at = now
            lease.save(update_fields=["status", "released_at"])
        raise ProviderRuntimeError("provider_lease_lost", "Provider lease has expired")
    lease.heartbeat_at = now
    lease.expires_at = now + timedelta(seconds=max(1, lease_seconds))
    lease.save(update_fields=["heartbeat_at", "expires_at"])
    return lease


@transaction.atomic
def release_provider_lease(lease_token: str, *, owner_id: str) -> AIProviderLease:
    lease = AIProviderLease.objects.select_for_update().filter(lease_token=lease_token).first()
    if lease is None or lease.owner_id != owner_id:
        raise ProviderRuntimeError("provider_lease_lost", "Provider lease is not owned by this runner")
    if lease.status == AIProviderLease.STATUS_ACTIVE:
        lease.status = AIProviderLease.STATUS_RELEASED
        lease.released_at = timezone.now()
        lease.save(update_fields=["status", "released_at"])
    return lease


def binding_requires_cli(binding: ProviderBinding) -> bool:
    return binding.target_id in {
        ProviderTarget.CODEX_SUBSCRIPTION.value,
        ProviderTarget.GROK_SUBSCRIPTION.value,
    }
