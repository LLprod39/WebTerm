"""One object-level authorization boundary for all playbook endpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef, Q, QuerySet
from django.utils import timezone

from core_ui.models.projects import ProjectMembership
from servers.models import Playbook, PlaybookGrant


@dataclass(frozen=True)
class PlaybookCapabilities:
    can_view: bool = False
    can_edit: bool = False
    can_validate: bool = False
    can_publish: bool = False
    can_run: bool = False
    can_export: bool = False
    can_share: bool = False
    can_delete: bool = False
    is_owner: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


OWNER_CAPABILITIES = PlaybookCapabilities(
    can_view=True,
    can_edit=True,
    can_validate=True,
    can_publish=True,
    can_run=True,
    can_export=True,
    can_share=True,
    can_delete=True,
    is_owner=True,
)


def _active_grants_q(now=None, *, prefix: str = "") -> Q:
    now = now or timezone.now()
    return Q(**{f"{prefix}revoked_at__isnull": True}) & (
        Q(**{f"{prefix}expires_at__isnull": True}) | Q(**{f"{prefix}expires_at__gt": now})
    )


def playbooks_visible_to(user) -> QuerySet[Playbook]:
    if not getattr(user, "is_authenticated", False):
        return Playbook.objects.none()
    group_ids = list(user.groups.values_list("id", flat=True))
    principal_q = Q(grants__user=user)
    if group_ids:
        principal_q |= Q(grants__group_id__in=group_ids)
    grant_q = (
        Q(project__memberships__user=user)
        & principal_q
        & Q(grants__can_view=True)
        & _active_grants_q(prefix="grants__")
    )
    workspace_grant_q = Q(
        project__memberships__user=user, grants__workspace_shared=True, grants__can_view=True
    ) & _active_grants_q(prefix="grants__")
    workspace_policy = PlaybookGrant.objects.filter(playbook_id=OuterRef("pk"), workspace_shared=True)
    return (
        Playbook.objects.annotate(_has_workspace_policy=Exists(workspace_policy))
        .filter(
            Q(user=user)
            | grant_q
            | workspace_grant_q
            | Q(
                project__memberships__user=user,
                visibility=Playbook.VISIBILITY_SHARED,
                origin_revision__isnull=True,
                _has_workspace_policy=False,
            )
        )
        .filter(is_archived=False)
        .select_related("origin_revision", "published_revision", "active_compatibility_revision", "draft")
        .distinct()
    )


def capabilities_for(playbook: Playbook, user) -> PlaybookCapabilities:
    if not getattr(user, "is_authenticated", False):
        return PlaybookCapabilities()
    if playbook.user_id == user.id:
        return OWNER_CAPABILITIES

    is_workspace_member = ProjectMembership.objects.filter(project_id=playbook.project_id, user=user).exists()
    if not is_workspace_member:
        return PlaybookCapabilities()

    group_ids = list(user.groups.values_list("id", flat=True))
    principal_q = Q(user=user)
    if group_ids:
        principal_q |= Q(group_id__in=group_ids)
    principal_q |= Q(workspace_shared=True)
    grants = PlaybookGrant.objects.filter(playbook=playbook).filter(_active_grants_q()).filter(principal_q)

    values = {
        "can_view": False,
        "can_edit": False,
        "can_validate": False,
        "can_publish": False,
        "can_run": False,
        "can_export": False,
        "can_share": False,
    }
    for grant in grants.only(
        "can_view",
        "can_edit",
        "can_validate",
        "can_publish",
        "can_run",
        "can_export",
        "can_manage_shares",
    ):
        values["can_view"] |= grant.can_view
        values["can_edit"] |= grant.can_edit
        values["can_validate"] |= grant.can_validate
        values["can_publish"] |= grant.can_publish
        values["can_run"] |= grant.can_run
        values["can_export"] |= grant.can_export
        values["can_share"] |= grant.can_manage_shares

    # Dual-read compatibility until every legacy shared row has a workspace grant.
    has_workspace_policy = PlaybookGrant.objects.filter(
        playbook=playbook,
        workspace_shared=True,
    ).exists()
    if (
        playbook.visibility == Playbook.VISIBILITY_SHARED
        and is_workspace_member
        and playbook.origin_revision_id is None
        and not has_workspace_policy
    ):
        values["can_view"] = True
        values["can_validate"] = True
        values["can_run"] = True
        values["can_export"] = True

    return PlaybookCapabilities(**values)


def require_playbook_capability(playbook: Playbook, user, capability: str) -> PlaybookCapabilities:
    capabilities = capabilities_for(playbook, user)
    attribute = capability if capability.startswith("can_") else f"can_{capability}"
    if not getattr(capabilities, attribute, False):
        raise PermissionDenied(f"Playbook capability required: {attribute}")
    return capabilities
