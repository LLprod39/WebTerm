"""Capability grant presets and audited share mutations."""

from __future__ import annotations

from django.contrib.auth import get_user_model
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
        "can_run": False,
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


def _project_role_for_grant(role: str) -> str:
    from core_ui.models.projects import ProjectMembership

    return ProjectMembership.ROLE_VIEWER if role == PlaybookGrant.ROLE_VIEWER else ProjectMembership.ROLE_OPERATOR


def _enroll_playbook_principals(playbook, *, role: str, user=None, group=None, include_all_users: bool = False) -> None:
    from core_ui.models.projects import ProjectMembership
    from core_ui.projects import activate_first_shared_project_if_personal_empty

    users = []
    if user is not None:
        users = [user]
    elif group is not None:
        users = list(group.user_set.filter(is_active=True))
    elif include_all_users:
        users = list(get_user_model().objects.filter(is_active=True).exclude(pk=playbook.user_id))
    project_role = _project_role_for_grant(role)
    for principal_user in users:
        membership, created = ProjectMembership.objects.get_or_create(
            project_id=playbook.project_id,
            user=principal_user,
            defaults={"role": project_role},
        )
        if not created and project_role == ProjectMembership.ROLE_OPERATOR and membership.role == "viewer":
            membership.role = ProjectMembership.ROLE_OPERATOR
            membership.save(update_fields=["role", "updated_at"])
        activate_first_shared_project_if_personal_empty(principal_user, playbook.project)


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
        _enroll_playbook_principals(
            playbook,
            role=PlaybookGrant.ROLE_OPERATOR,
            include_all_users=True,
        )
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
    if user is not None and user.id == playbook.user_id:
        raise PlaybookGrantError("The owner already has every capability")
    if expires_at is not None and expires_at <= timezone.now():
        raise PlaybookGrantError("Share expiry must be in the future")

    principal = _principal_kwargs(user=user, group=group, workspace_shared=workspace_shared)
    lookup = {"playbook": playbook}
    if principal["user"] is not None:
        lookup["user"] = principal["user"]
    elif principal["group"] is not None:
        lookup["group"] = principal["group"]
    else:
        lookup["workspace_shared"] = True

    capabilities = dict(ROLE_CAPABILITIES[role])
    for key, value in (capability_overrides or {}).items():
        if key in capabilities:
            capabilities[key] = bool(value)
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
    _enroll_playbook_principals(playbook, role=role, user=user, group=group)
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
