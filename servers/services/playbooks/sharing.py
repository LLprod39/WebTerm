"""Capability grant presets and audited share mutations."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from servers.models import PlaybookGrant
from servers.services.playbooks.audit import record_playbook_event

ROLE_CAPABILITIES = {
    PlaybookGrant.ROLE_VIEWER: {
        "can_view": True,
        "can_edit": False,
        "can_validate": False,
        "can_publish": False,
        "can_run": False,
        "can_export": False,
        "can_manage_shares": False,
    },
    PlaybookGrant.ROLE_EDITOR: {
        "can_view": True,
        "can_edit": True,
        "can_validate": True,
        "can_publish": False,
        "can_run": True,
        "can_export": True,
        "can_manage_shares": False,
    },
    PlaybookGrant.ROLE_OPERATOR: {
        "can_view": True,
        "can_edit": False,
        "can_validate": True,
        "can_publish": False,
        "can_run": True,
        "can_export": True,
        "can_manage_shares": False,
    },
    PlaybookGrant.ROLE_MANAGER: {
        "can_view": True,
        "can_edit": True,
        "can_validate": True,
        "can_publish": True,
        "can_run": True,
        "can_export": True,
        "can_manage_shares": True,
    },
}


class PlaybookGrantError(ValueError):
    pass


def _require_existing_project_principal(playbook, *, user=None, group=None) -> None:
    from core_ui.models.projects import ProjectMembership

    if user is not None:
        if not ProjectMembership.objects.filter(project_id=playbook.project_id, user=user).exists():
            raise PlaybookGrantError("User is not a member of this project")
        return
    if group is None:
        return
    active_user_ids = set(group.user_set.filter(is_active=True).values_list("id", flat=True))
    if not active_user_ids:
        raise PlaybookGrantError("Group has no active project members")
    member_ids = set(
        ProjectMembership.objects.filter(project_id=playbook.project_id, user_id__in=active_user_ids).values_list(
            "user_id", flat=True
        )
    )
    if member_ids != active_user_ids:
        raise PlaybookGrantError("Every active group user must already be a project member")


@transaction.atomic
def sync_legacy_visibility_grant(playbook, *, actor) -> PlaybookGrant | None:
    """Dual-write the old shared flag without overriding an explicit V2 policy."""
    existing = (
        PlaybookGrant.objects.select_for_update()
        .filter(
            playbook=playbook,
            workspace_shared=True,
        )
        .first()
    )
    if playbook.visibility == "shared":
        if existing is not None:
            if existing.is_legacy and existing.revoked_at is not None:
                existing.revoked_at = None
                existing.role = PlaybookGrant.ROLE_OPERATOR
                for name, value in ROLE_CAPABILITIES[PlaybookGrant.ROLE_OPERATOR].items():
                    setattr(existing, name, value)
                existing.save()
            return existing
        capabilities = ROLE_CAPABILITIES[PlaybookGrant.ROLE_OPERATOR]
        return PlaybookGrant.objects.create(
            playbook=playbook,
            workspace_shared=True,
            role=PlaybookGrant.ROLE_OPERATOR,
            **capabilities,
            granted_by=actor,
            is_legacy=True,
        )
    if existing is not None and existing.is_legacy and existing.revoked_at is None:
        existing.revoked_at = timezone.now()
        existing.save(update_fields=["revoked_at", "updated_at"])
    return existing


def _principal_kwargs(*, user=None, group=None, workspace_shared: bool = False) -> dict:
    selected = int(user is not None) + int(group is not None) + int(bool(workspace_shared))
    if selected != 1:
        raise PlaybookGrantError("Exactly one share principal is required")
    if user is not None:
        return {"user": user, "group": None, "workspace_shared": False}
    if group is not None:
        return {"user": None, "group": group, "workspace_shared": False}
    return {"user": None, "group": None, "workspace_shared": True}


@transaction.atomic
def save_grant(
    *,
    playbook,
    actor,
    role: str,
    user=None,
    group=None,
    workspace_shared: bool = False,
    expires_at=None,
    capability_overrides: dict | None = None,
) -> PlaybookGrant:
    if role not in ROLE_CAPABILITIES:
        raise PlaybookGrantError("Unknown playbook share role")
    if workspace_shared:
        raise PlaybookGrantError("New workspace-wide playbook grants are not allowed")
    if user is not None and user.id == playbook.user_id:
        raise PlaybookGrantError("The owner already has every capability")
    if expires_at is not None and expires_at <= timezone.now():
        raise PlaybookGrantError("Share expiry must be in the future")

    principal = _principal_kwargs(user=user, group=group, workspace_shared=False)
    _require_existing_project_principal(playbook, user=user, group=group)
    from servers.services.playbooks.revision_safety import validate_revision_safety
    from servers.services.playbooks.revisions import ensure_playbook_workspace

    published = playbook.published_revision
    if published is None:
        published, _draft = ensure_playbook_workspace(playbook, actor=actor)
    validate_revision_safety(published)
    lookup = {"playbook": playbook}
    if principal["user"] is not None:
        lookup["user"] = principal["user"]
    elif principal["group"] is not None:
        lookup["group"] = principal["group"]
    else:
        lookup["workspace_shared"] = True

    capabilities = dict(ROLE_CAPABILITIES[role])
    for key, value in (capability_overrides or {}).items():
        if key not in capabilities or bool(value) != capabilities[key]:
            raise PlaybookGrantError("Playbook share capabilities are fixed by role")
    grant, _created = PlaybookGrant.objects.update_or_create(
        **lookup,
        defaults={
            **principal,
            **capabilities,
            "role": role,
            "granted_by": actor,
            "expires_at": expires_at,
            "revoked_at": None,
            "is_legacy": False,
        },
    )
    record_playbook_event(
        playbook=playbook,
        actor=actor,
        event_type="share_saved",
        entity_type="grant",
        entity_id=grant.id,
        metadata={
            "role": role,
            "principal_type": "user" if grant.user_id else "group" if grant.group_id else "workspace",
            "principal_id": grant.user_id or grant.group_id,
            "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        },
    )
    return grant


@transaction.atomic
def revoke_grant(grant: PlaybookGrant, *, actor) -> PlaybookGrant:
    locked = PlaybookGrant.objects.select_for_update().get(pk=grant.pk)
    if locked.revoked_at is None:
        locked.revoked_at = timezone.now()
        locked.save(update_fields=["revoked_at", "updated_at"])
        record_playbook_event(
            playbook=locked.playbook,
            actor=actor,
            event_type="share_revoked",
            entity_type="grant",
            entity_id=locked.id,
            metadata={"role": locked.role},
        )
    return locked


def serialize_grant(grant: PlaybookGrant) -> dict:
    return {
        "id": grant.id,
        "role": grant.role,
        "principal": {
            "type": "user" if grant.user_id else "group" if grant.group_id else "workspace",
            "id": grant.user_id or grant.group_id,
            "label": grant.principal_label,
        },
        "capabilities": {
            "can_view": grant.can_view,
            "can_edit": grant.can_edit,
            "can_validate": grant.can_validate,
            "can_publish": grant.can_publish,
            "can_run": grant.can_run,
            "can_export": grant.can_export,
            "can_manage_shares": grant.can_manage_shares,
        },
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
        "is_legacy": grant.is_legacy,
        "created_at": grant.created_at.isoformat(),
    }
