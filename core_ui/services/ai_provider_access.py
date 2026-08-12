"""Default-deny access checks for personal and workspace CLI connections."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models import Q

from app.ai_runtime import ExecutionMode, ProviderBinding, ProviderTarget
from core_ui.models.ai_providers import AIProviderConnection, AIProviderPool
from core_ui.models.projects import ProjectMembership


@dataclass(frozen=True, slots=True)
class ConnectionAccessDecision:
    allowed: bool
    reason: str = ""

    def as_route_decision(self) -> tuple[bool, str]:
        return self.allowed, self.reason


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

    mode_filter = Q(allow_unattended=True) if mode is ExecutionMode.UNATTENDED else Q(allow_interactive=True)
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

    if connection.grants.filter(mode_filter & principal_filter).exists():
        return ConnectionAccessDecision(True)
    return ConnectionAccessDecision(False, "no matching connection grant")


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
    }:
        return ConnectionAccessDecision(False, "subscription binding requires a connection or pool")

    # Platform API/local targets have their own existing feature permissions
    # and visibility controls. This service only governs subscription accounts.
    return ConnectionAccessDecision(True)
