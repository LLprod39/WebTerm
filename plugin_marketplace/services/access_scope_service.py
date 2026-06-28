from __future__ import annotations

from typing import Any

from django.contrib.auth.models import Group
from django.db import transaction

from core_ui.models import UserActivityLog
from plugin_marketplace.models import PluginInstallation


def group_payload(group: Group) -> dict[str, Any]:
    return {"id": group.id, "name": group.name}


def installation_scope_payload(installation: PluginInstallation) -> dict[str, Any]:
    groups = sorted(installation.scoped_groups.all(), key=lambda item: item.name.lower())
    return {
        "mode": "groups" if groups else "global",
        "groups": [group_payload(group) for group in groups],
        "group_ids": [group.id for group in groups],
    }


def installation_allowed_for_user(installation: PluginInstallation, user) -> bool:
    groups = list(installation.scoped_groups.all())
    if not groups:
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    scoped_ids = {group.id for group in groups}
    return user.groups.filter(id__in=scoped_ids).exists()


@transaction.atomic
def update_installation_scope(
    installation_id: int,
    group_ids: list[int],
    *,
    actor=None,
    request=None,
) -> PluginInstallation:
    installation = PluginInstallation.objects.select_for_update().get(id=installation_id)
    normalized_ids = sorted({int(group_id) for group_id in group_ids})
    groups = list(Group.objects.filter(id__in=normalized_ids).order_by("name"))
    found_ids = {group.id for group in groups}
    missing = [group_id for group_id in normalized_ids if group_id not in found_ids]
    if missing:
        raise ValueError(f"Unknown access group ids: {', '.join(str(item) for item in missing)}")

    installation.scoped_groups.set(groups)

    from plugin_marketplace.services.install_service import record_event

    record_event(
        plugin_id=installation.plugin_id,
        event_type="plugin_scope_updated",
        status=UserActivityLog.STATUS_SUCCESS,
        actor=actor,
        request=request,
        installation=installation,
        message=(
            f"Plugin {installation.plugin_id} scoped to {len(groups)} access group(s)."
            if groups
            else f"Plugin {installation.plugin_id} scope reset to global."
        ),
        metadata={
            "group_ids": [group.id for group in groups],
            "group_names": [group.name for group in groups],
            "scope_mode": "groups" if groups else "global",
        },
    )
    return installation
