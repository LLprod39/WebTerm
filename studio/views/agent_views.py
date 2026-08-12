"""
Studio agent configuration endpoints.
"""

import json

from django.http import JsonResponse

from app.ai_runtime import ExecutionMode
from app.sudo_policy import normalize_sudo_policy
from core_ui.decorators import require_feature
from core_ui.projects import active_project_for_user
from core_ui.services.ai_execution_context import build_execution_context
from studio.models import AgentConfig
from studio.views.agent_helpers import (
    _agent_read_queryset_for_user,
    _agent_to_dict,
    _set_accessible_mcp_servers,
    _set_owned_server_scope,
)
from studio.views.common import _apply_shared_users, _is_admin, _normalise_related_ids
from studio.views.skill_helpers import _normalise_skill_payload, _sanitize_accessible_skill_slugs

STUDIO_FEATURE_AGENTS = "studio_agents"


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


@require_feature(STUDIO_FEATURE_AGENTS)
def api_agents(request):
    if request.method == "GET":
        qs = _agent_read_queryset_for_user(request.user)
        return _ok([_agent_to_dict(agent, request.user) for agent in qs])

    if request.method == "POST":
        data = _json_body(request)
        name = data.get("name", "").strip()
        if not name:
            return _err("name is required")
        provider_binding = {}
        if data.get("provider_binding"):
            try:
                project = active_project_for_user(request.user)
                context = build_execution_context(
                    actor_user_id=request.user.pk,
                    project_id=project.pk if project else None,
                    purpose="ops",
                    source_kind="pipeline",
                    source_id="new-agent-config",
                    mode=ExecutionMode.UNATTENDED,
                    explicit_binding=data.get("provider_binding"),
                )
                provider_binding = context.binding.to_dict()
            except (TypeError, ValueError, RuntimeError) as exc:
                return _err(str(exc))
        requested_mcp_ids = _normalise_related_ids(
            data.get("mcp_server_ids") if "mcp_server_ids" in data else data.get("mcp_servers")
        )
        agent = AgentConfig.objects.create(
            name=name,
            description=data.get("description", ""),
            icon=data.get("icon", "🤖"),
            system_prompt=data.get("system_prompt", ""),
            instructions=data.get("instructions", ""),
            model=data.get("model", "gemini-2.0-flash-exp"),
            max_iterations=data.get("max_iterations", 10),
            allowed_tools=data.get("allowed_tools", []),
            sudo_policy=normalize_sudo_policy(data.get("sudo_policy")),
            skill_slugs=_sanitize_accessible_skill_slugs(
                request.user,
                _normalise_skill_payload(data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")),
            ),
            owner=request.user,
            provider_binding=provider_binding,
        )
        _set_accessible_mcp_servers(agent, request.user, requested_mcp_ids)
        _set_owned_server_scope(
            agent,
            request.user,
            _normalise_related_ids(
                data.get("server_scope_ids") if "server_scope_ids" in data else data.get("server_scope")
            ),
        )
        if _is_admin(request.user):
            agent.is_shared = bool(data.get("is_shared", agent.is_shared))
            agent.save(update_fields=["is_shared"])
            _apply_shared_users(agent, _normalise_related_ids(data.get("shared_user_ids")))
        return _ok(_agent_to_dict(agent, request.user), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_AGENTS)
def api_agent_detail(request, agent_id: int):
    agent = _agent_read_queryset_for_user(request.user).filter(pk=agent_id).first()
    if agent is None:
        return _err("Agent config not found", 404)
    can_edit = _is_admin(request.user) or agent.owner_id == request.user.id

    if request.method == "GET":
        return _ok(_agent_to_dict(agent, request.user))

    if request.method == "PUT":
        if not can_edit:
            return _err("Only the owner or admin can edit this agent", 403)
        data = _json_body(request)
        for field in (
            "name",
            "description",
            "icon",
            "system_prompt",
            "instructions",
            "model",
            "max_iterations",
            "allowed_tools",
        ):
            if field in data:
                setattr(agent, field, data[field])
        if "sudo_policy" in data:
            agent.sudo_policy = normalize_sudo_policy(data.get("sudo_policy"))
        if "provider_binding" in data:
            if data.get("provider_binding") in ({}, None):
                agent.provider_binding = {}
            else:
                try:
                    context = build_execution_context(
                        actor_user_id=request.user.pk,
                        project_id=agent.project_id,
                        purpose="ops",
                        source_kind="pipeline",
                        source_id=f"agent-config:{agent.pk}",
                        mode=ExecutionMode.UNATTENDED,
                        explicit_binding=data.get("provider_binding"),
                    )
                    agent.provider_binding = context.binding.to_dict()
                except (TypeError, ValueError, RuntimeError) as exc:
                    return _err(str(exc))
        if "skill_slugs" in data or "skills" in data:
            agent.skill_slugs = _sanitize_accessible_skill_slugs(
                request.user,
                _normalise_skill_payload(data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")),
            )
        agent.save()
        if "mcp_server_ids" in data or "mcp_servers" in data:
            requested_mcp_ids = _normalise_related_ids(
                data.get("mcp_server_ids") if "mcp_server_ids" in data else data.get("mcp_servers")
            )
            _set_accessible_mcp_servers(agent, request.user, requested_mcp_ids)
        if "server_scope_ids" in data or "server_scope" in data:
            _set_owned_server_scope(
                agent,
                request.user,
                _normalise_related_ids(
                    data.get("server_scope_ids") if "server_scope_ids" in data else data.get("server_scope")
                ),
            )
        if _is_admin(request.user):
            if "is_shared" in data:
                agent.is_shared = bool(data.get("is_shared"))
                agent.save(update_fields=["is_shared"])
            if "shared_user_ids" in data:
                _apply_shared_users(agent, _normalise_related_ids(data.get("shared_user_ids")))
        return _ok(_agent_to_dict(agent, request.user))

    if request.method == "DELETE":
        if not can_edit:
            return _err("Only the owner or admin can delete this agent", 403)
        agent.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)
