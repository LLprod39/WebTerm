"""
Shared helpers for Studio agent endpoints.
"""

from django.db.models import Q

from studio.models import AgentConfig
from studio.services import get_owned_servers_by_ids
from studio.skill_policy import compile_skill_policies
from studio.skill_registry import resolve_skills
from studio.views.common import (
    STUDIO_FEATURE_MCP,
    _access_mode,
    _is_admin,
    _owner_payload,
    _shared_user_payloads,
    _user_has_feature,
)
from studio.views.mcp_views import _mcp_read_queryset_for_user
from studio.views.skill_helpers import _get_skill_access, _skill_to_summary_dict


def _agent_read_queryset_for_user(user):
    qs = AgentConfig.objects.select_related("owner").prefetch_related("mcp_servers", "server_scope", "shared_with")
    if _is_admin(user):
        return qs.order_by("-updated_at")
    return qs.filter(Q(owner=user) | Q(is_shared=True) | Q(shared_with=user)).distinct().order_by("-updated_at")


def _agent_write_queryset_for_user(user):
    qs = AgentConfig.objects.select_related("owner").prefetch_related("mcp_servers", "server_scope", "shared_with")
    if _is_admin(user):
        return qs
    return qs.filter(owner=user)


def _agent_to_dict(agent: AgentConfig, viewer) -> dict:
    skills, skill_errors = resolve_skills(agent.skill_slugs or [])
    _, policy_errors = compile_skill_policies(skills)
    shared_users = _shared_user_payloads(agent.shared_with.all())
    return {
        "id": agent.pk,
        "name": agent.name,
        "description": agent.description,
        "icon": agent.icon,
        "system_prompt": agent.system_prompt,
        "instructions": agent.instructions,
        "model": agent.model,
        "max_iterations": agent.max_iterations,
        "allowed_tools": agent.allowed_tools,
        "mcp_servers": list(agent.mcp_servers.all().values("id", "name", "transport")),
        "skill_slugs": list(agent.skill_slugs or []),
        "skills": [_skill_to_summary_dict(skill, viewer, _get_skill_access(skill.slug)) for skill in skills],
        "skill_errors": [*skill_errors, *policy_errors],
        "server_scope": list(agent.server_scope.all().values("id", "name")),
        "owner": _owner_payload(agent.owner),
        "owner_username": agent.owner.username,
        "is_owner": agent.owner_id == getattr(viewer, "id", None),
        "can_edit": _is_admin(viewer) or agent.owner_id == getattr(viewer, "id", None),
        "can_share": _is_admin(viewer),
        "is_shared": bool(agent.is_shared or shared_users),
        "shared_user_ids": [item["id"] for item in shared_users],
        "shared_users": shared_users,
        "access_mode": _access_mode(owner_id=agent.owner_id, viewer=viewer),
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def _set_accessible_mcp_servers(agent: AgentConfig, user, ids: list[int] | None):
    if not _user_has_feature(user, STUDIO_FEATURE_MCP):
        agent.mcp_servers.set([])
        return
    requested_ids = ids or []
    items = list(_mcp_read_queryset_for_user(user).filter(pk__in=requested_ids))
    agent.mcp_servers.set(items)


def _set_owned_server_scope(agent: AgentConfig, owner, ids: list[int] | None):
    items = get_owned_servers_by_ids(owner, ids)
    agent.server_scope.set(items)
