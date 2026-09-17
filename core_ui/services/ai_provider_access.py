"""Default-deny access checks for personal and workspace CLI connections."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from app.ai_runtime import ExecutionMode, ProviderBinding, ProviderRuntimeError, ProviderTarget
from core_ui.models.ai_providers import (
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderLease,
    AIProviderPool,
)
from core_ui.models.projects import ProjectMembership


@dataclass(frozen=True, slots=True)
class ConnectionAccessDecision:
    allowed: bool
    reason: str = ""

    def as_route_decision(self) -> tuple[bool, str]:
        return self.allowed, self.reason


def _mode_filter(mode: ExecutionMode) -> Q:
    if mode is ExecutionMode.UNATTENDED:
        return Q(allow_unattended=True)
    return Q(allow_interactive=True)


def _principal_filter(*, user_id: int, project_id: int | None) -> Q:
    principal_filter = Q(user_id=user_id)
    group_ids = get_user_model().objects.filter(pk=user_id).values_list("groups__id", flat=True)
    principal_filter |= Q(group_id__in=group_ids)

    if project_id is not None:
        membership = (
            ProjectMembership.objects.filter(
                project_id=project_id,
                user_id=user_id,
            )
            .values_list("role", flat=True)
            .first()
        )
        project_filter = Q(project_id=project_id, project_role="")
        if membership:
            project_filter |= Q(project_id=project_id, project_role=membership)
        principal_filter |= project_filter
    return principal_filter


def matching_grants(
    connection: AIProviderConnection,
    *,
    user_id: int,
    project_id: int | None,
    mode: ExecutionMode,
) -> QuerySet[AIProviderConnectionGrant]:
    """Workspace grants that authorize this user for the given mode."""
    return connection.grants.filter(_mode_filter(mode) & _principal_filter(user_id=user_id, project_id=project_id))


def can_use_connection(
    connection: AIProviderConnection,
    *,
    user_id: int | None,
    project_id: int | None,
    mode: ExecutionMode,
) -> ConnectionAccessDecision:
    if not connection.enabled:
        return ConnectionAccessDecision(False, "connection is disabled")
    if connection.status != AIProviderConnection.STATUS_CONNECTED:
        return ConnectionAccessDecision(False, f"connection status is {connection.status}")
    if user_id is None:
        return ConnectionAccessDecision(False, "an authenticated user is required")

    if connection.scope == AIProviderConnection.SCOPE_PERSONAL:
        if connection.owner_id != user_id:
            return ConnectionAccessDecision(False, "personal connection belongs to another user")
        return ConnectionAccessDecision(True)

    if matching_grants(connection, user_id=user_id, project_id=project_id, mode=mode).exists():
        return ConnectionAccessDecision(True)
    return ConnectionAccessDecision(False, "no matching connection grant")


def _active_lease_user_ids(connection: AIProviderConnection) -> list[int]:
    return list(
        connection.leases.filter(status=AIProviderLease.STATUS_ACTIVE, invocation__user_id__isnull=False).values_list(
            "invocation__user_id", flat=True
        )
    )


def assert_principal_capacity(
    connection: AIProviderConnection,
    *,
    user_id: int | None,
    project_id: int | None,
    mode: ExecutionMode,
) -> None:
    """Enforce grant max_slots on top of connection.concurrency_limit.

    User grant: personal concurrent ceiling for this user on the connection.
    Group grant: shared concurrent pool for all members of that group.
    All matching grants with max_slots set must pass (AND).
    """
    if connection.scope != AIProviderConnection.SCOPE_WORKSPACE:
        return
    if user_id is None:
        return

    grants = list(matching_grants(connection, user_id=user_id, project_id=project_id, mode=mode))
    limited = [grant for grant in grants if grant.max_slots]
    if not limited:
        return

    active_user_ids = _active_lease_user_ids(connection)
    user_active = sum(1 for uid in active_user_ids if uid == user_id)

    for grant in limited:
        if grant.user_id is not None:
            if user_active >= int(grant.max_slots):
                raise ProviderRuntimeError(
                    "provider_principal_capacity_unavailable",
                    "User has no free execution slots on this provider connection",
                    retryable=True,
                    details={
                        "connection_id": connection.pk,
                        "grant_id": grant.pk,
                        "max_slots": grant.max_slots,
                        "active": user_active,
                    },
                )
            continue

        if grant.group_id is not None:
            member_ids = set(
                get_user_model().objects.filter(groups__id=grant.group_id).values_list("id", flat=True)
            )
            group_active = sum(1 for uid in active_user_ids if uid in member_ids)
            if group_active >= int(grant.max_slots):
                raise ProviderRuntimeError(
                    "provider_principal_capacity_unavailable",
                    "Group has no free execution slots on this provider connection",
                    retryable=True,
                    details={
                        "connection_id": connection.pk,
                        "grant_id": grant.pk,
                        "group_id": grant.group_id,
                        "max_slots": grant.max_slots,
                        "active": group_active,
                    },
                )
            continue

        # Project grants: treat max_slots as a shared ceiling for users covered by this grant.
        # Count all active leases on the connection that belong to users who still match this grant.
        # Simpler v1: count all active leases on the connection against project grant max_slots.
        project_active = len(active_user_ids)
        if project_active >= int(grant.max_slots):
            raise ProviderRuntimeError(
                "provider_principal_capacity_unavailable",
                "Project grant has no free execution slots on this provider connection",
                retryable=True,
                details={
                    "connection_id": connection.pk,
                    "grant_id": grant.pk,
                    "max_slots": grant.max_slots,
                    "active": project_active,
                },
            )


def principal_has_capacity(
    connection: AIProviderConnection,
    *,
    user_id: int | None,
    project_id: int | None,
    mode: ExecutionMode,
) -> bool:
    try:
        assert_principal_capacity(connection, user_id=user_id, project_id=project_id, mode=mode)
    except ProviderRuntimeError:
        return False
    return True


def can_use_binding(
    binding: ProviderBinding,
    *,
    user_id: int | None,
    project_id: int | None,
    mode: ExecutionMode,
) -> ConnectionAccessDecision:
    if binding.connection_id is not None:
        connection = AIProviderConnection.objects.filter(pk=binding.connection_id).first()
        if connection is None:
            return ConnectionAccessDecision(False, "connection does not exist")
        if connection.target_id != binding.target_id:
            return ConnectionAccessDecision(False, "connection target does not match binding")
        return can_use_connection(connection, user_id=user_id, project_id=project_id, mode=mode)

    if binding.pool_id is not None:
        pool = AIProviderPool.objects.filter(pk=binding.pool_id, enabled=True).first()
        if pool is None:
            return ConnectionAccessDecision(False, "pool does not exist or is disabled")
        if pool.target_id != binding.target_id:
            return ConnectionAccessDecision(False, "pool target does not match binding")
        members = AIProviderConnection.objects.filter(
            pool_memberships__pool=pool,
            pool_memberships__enabled=True,
            enabled=True,
            status=AIProviderConnection.STATUS_CONNECTED,
        ).distinct()
        for connection in members:
            decision = can_use_connection(connection, user_id=user_id, project_id=project_id, mode=mode)
            if decision.allowed:
                return decision
        return ConnectionAccessDecision(False, "pool has no accessible healthy member")

    if binding.target_id in {
        ProviderTarget.CODEX_SUBSCRIPTION.value,
        ProviderTarget.GROK_SUBSCRIPTION.value,
        ProviderTarget.CURSOR_SUBSCRIPTION.value,
    }:
        return ConnectionAccessDecision(False, "subscription binding requires a connection or pool")

    # Platform API/local targets have their own existing feature permissions
    # and visibility controls. This service only governs subscription accounts.
    return ConnectionAccessDecision(True)
