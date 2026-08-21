"""Creation, consistency validation, ACL, and agent binding for memory assets."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from servers.models import (
    ServerMemoryAsset,
    ServerMemoryAssetAgentBinding,
    ServerMemoryAssetGrant,
    ServerMemorySnapshot,
)

READABLE_GRANT_PERMISSIONS = {
    ServerMemoryAssetGrant.PERMISSION_READ,
    ServerMemoryAssetGrant.PERMISSION_USE,
    ServerMemoryAssetGrant.PERMISSION_MANAGE,
}


def has_memory_management_boundary(*, actor, server) -> bool:
    """Match the existing memory UI boundary: staff operating an owned server."""
    return bool(
        getattr(actor, "is_authenticated", False)
        and getattr(actor, "is_staff", False)
        and getattr(server, "user_id", None) == getattr(actor, "pk", None)
    )


@transaction.atomic
def create_memory_asset(
    *,
    server,
    stable_key: str,
    title: str,
    current_snapshot: ServerMemorySnapshot,
    created_by,
    asset_kind: str = ServerMemoryAsset.KIND_NOTE,
    visibility: str = ServerMemoryAsset.VISIBILITY_INHERIT_SERVER,
    lifecycle: str = ServerMemoryAsset.LIFECYCLE_CANDIDATE,
    approved_by=None,
    generation_log=None,
    source_ref: str = "",
) -> ServerMemoryAsset:
    """Create one consistent logical asset without touching legacy snapshots."""
    cleaned_key = str(stable_key or "").strip()[:120]
    if not cleaned_key:
        raise ValueError("stable_key is required")
    _validate_choice(asset_kind, ServerMemoryAsset.KIND_CHOICES, "asset kind")
    _validate_choice(visibility, ServerMemoryAsset.VISIBILITY_CHOICES, "visibility")
    _validate_choice(lifecycle, ServerMemoryAsset.LIFECYCLE_CHOICES, "lifecycle")
    if current_snapshot.server_id != server.id:
        raise ValueError("Current snapshot must belong to the asset server")
    if current_snapshot.asset_id is not None:
        raise ValueError("Current snapshot is already linked to a memory asset")
    if server.project_id is None:
        raise ValueError("Server project is required")
    if generation_log is not None and generation_log.server_id != server.id:
        raise ValueError("Generation log must belong to the asset server")
    if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED:
        if current_snapshot.layer != ServerMemorySnapshot.LAYER_CANONICAL:
            raise ValueError("Approved assets require a canonical snapshot")
        if approved_by is None or not has_memory_management_boundary(actor=approved_by, server=server):
            raise ValueError("Approved assets require an authorized staff owner")

    asset = ServerMemoryAsset.objects.create(
        project_id=server.project_id,
        server=server,
        current_snapshot=current_snapshot,
        created_by=created_by,
        approved_by=approved_by,
        generation_log=generation_log,
        stable_key=cleaned_key,
        asset_kind=asset_kind,
        visibility=visibility,
        lifecycle=lifecycle,
        title=str(title or cleaned_key)[:200],
        source_ref=str(source_ref or "")[:255],
        approved_at=timezone.now() if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED else None,
    )
    current_snapshot.asset = asset
    current_snapshot.save(update_fields=["asset", "updated_at"])
    return asset


@transaction.atomic
def set_current_asset_snapshot(*, asset: ServerMemoryAsset, snapshot: ServerMemorySnapshot) -> ServerMemoryAsset:
    """Advance an asset to a validated snapshot version."""
    validate_asset_consistency(asset)
    if snapshot.server_id != asset.server_id:
        raise ValueError("Snapshot server does not match asset server")
    if snapshot.asset_id not in {None, asset.id}:
        raise ValueError("Snapshot belongs to a different memory asset")
    if snapshot.asset_id is None:
        snapshot.asset = asset
        snapshot.save(update_fields=["asset", "updated_at"])
    if asset.current_snapshot_id != snapshot.id:
        asset.current_snapshot = snapshot
        asset.save(update_fields=["current_snapshot", "updated_at"])
    return asset


@transaction.atomic
def bind_memory_asset_to_agent(
    *,
    asset: ServerMemoryAsset,
    agent,
    bound_by,
    injection_mode: str = ServerMemoryAssetAgentBinding.INJECTION_REFERENCE,
    priority: int = 100,
    enabled: bool = True,
    pinned_snapshot: ServerMemorySnapshot | None = None,
) -> ServerMemoryAssetAgentBinding:
    """Bind an asset after validating project/server/snapshot consistency."""
    validate_asset_consistency(asset)
    if agent.project_id != asset.project_id:
        raise ValueError("Agent project does not match memory asset project")
    if getattr(agent, "user_id", None) != getattr(bound_by, "pk", None):
        raise ValueError("Only the agent owner may bind memory assets")
    if not has_memory_management_boundary(actor=bound_by, server=asset.server):
        raise ValueError("Binding requires the authorized staff server owner")
    if not agent.servers.filter(pk=asset.server_id).exists():
        raise ValueError("Memory asset server must be in the agent server scope")
    if injection_mode not in {item[0] for item in ServerMemoryAssetAgentBinding.INJECTION_MODE_CHOICES}:
        raise ValueError("Unsupported injection mode")
    if pinned_snapshot is not None and (
        pinned_snapshot.server_id != asset.server_id or pinned_snapshot.asset_id != asset.id
    ):
        raise ValueError("Pinned snapshot must belong to the bound asset")
    binding, _created = ServerMemoryAssetAgentBinding.objects.update_or_create(
        asset=asset,
        agent=agent,
        defaults={
            "bound_by": bound_by,
            "pinned_snapshot": pinned_snapshot,
            "injection_mode": injection_mode,
            "priority": max(0, min(int(priority), 65_535)),
            "enabled": bool(enabled),
        },
    )
    return binding


def accessible_memory_assets_queryset(*, user, server_ids: list[int], project=None, agent=None) -> QuerySet:
    """Central deny-by-default asset ACL for already authorized server ids.

    ``project`` is retained as a compatibility argument for older callers, but
    it is no longer the user-facing selection boundary. Ownership, server
    shares and explicit asset grants are the authorization boundary.
    """
    if not server_ids:
        return ServerMemoryAsset.objects.none()
    if agent is not None and getattr(agent, "user_id", None) != getattr(user, "pk", None):
        return ServerMemoryAsset.objects.none()
    if agent is not None:
        server_ids = list(agent.servers.filter(pk__in=server_ids).values_list("pk", flat=True))
        if not server_ids:
            return ServerMemoryAsset.objects.none()

    now = timezone.now()
    active_grant_q = Q(grants__revoked_at__isnull=True) & (
        Q(grants__expires_at__isnull=True) | Q(grants__expires_at__gt=now)
    ) & Q(grants__permission__in=READABLE_GRANT_PERMISSIONS)
    visibility_q = Q(visibility=ServerMemoryAsset.VISIBILITY_INHERIT_SERVER)
    visibility_q |= Q(visibility=ServerMemoryAsset.VISIBILITY_PRIVATE) & (
        Q(server__user=user) | Q(created_by=user)
    )
    visibility_q |= Q(visibility=ServerMemoryAsset.VISIBILITY_PROJECT) & (
        Q(project__owner=user) | Q(project__memberships__user=user)
    )

    restricted_subject_q = Q(server__user=user) | Q(created_by=user)
    restricted_subject_q |= active_grant_q & Q(grants__user=user)
    group_ids = list(user.groups.values_list("id", flat=True))
    if group_ids:
        restricted_subject_q |= active_grant_q & Q(grants__group_id__in=group_ids)
    visibility_q |= Q(visibility=ServerMemoryAsset.VISIBILITY_RESTRICTED) & restricted_subject_q
    if agent is not None:
        visibility_q |= Q(
            visibility=ServerMemoryAsset.VISIBILITY_AGENT,
            agent_bindings__agent=agent,
            agent_bindings__enabled=True,
        )

    queryset = ServerMemoryAsset.objects.filter(server_id__in=server_ids).filter(visibility_q)
    if agent is not None:
        queryset = queryset.filter(project_id=agent.project_id)
    return queryset.distinct()


def validate_asset_consistency(asset: ServerMemoryAsset) -> None:
    if asset.project_id != asset.server.project_id:
        raise ValueError("Memory asset project does not match server project")
    if asset.current_snapshot_id and asset.current_snapshot.server_id != asset.server_id:
        raise ValueError("Current snapshot server does not match asset server")
    if asset.current_snapshot_id and asset.current_snapshot.asset_id != asset.id:
        raise ValueError("Current snapshot is not linked back to the memory asset")


def asset_is_consistent(asset: ServerMemoryAsset) -> bool:
    try:
        validate_asset_consistency(asset)
    except (AttributeError, ValueError):
        return False
    return True


def _validate_choice(value: str, choices, label: str) -> None:
    if value not in {choice[0] for choice in choices}:
        raise ValueError(f"Unsupported memory asset {label}")
