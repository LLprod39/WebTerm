"""
Agent Studio REST API Views

All endpoints require authentication (session or token).
Base URL: /api/studio/

Endpoints:
  GET  /api/studio/pipelines/               — list pipelines
  POST /api/studio/pipelines/               — create pipeline
  GET  /api/studio/pipelines/<id>/          — get pipeline detail
  PUT  /api/studio/pipelines/<id>/          — update pipeline
  DELETE /api/studio/pipelines/<id>/        — delete pipeline
  POST /api/studio/pipelines/<id>/run/      — trigger manual run
  POST /api/studio/pipelines/<id>/clone/    — clone pipeline
  GET  /api/studio/pipelines/<id>/runs/     — list runs for pipeline

  GET  /api/studio/runs/                    — list all runs (user)
  GET  /api/studio/runs/<id>/              — get run detail
  POST /api/studio/runs/<id>/stop/         — stop running pipeline

  GET  /api/studio/agents/                  — list agent configs
  POST /api/studio/agents/                  — create agent config
  GET  /api/studio/agents/<id>/             — get agent config
  PUT  /api/studio/agents/<id>/             — update agent config
  DELETE /api/studio/agents/<id>/           — delete agent config
  GET  /api/studio/skills/                  — list available skill packs
  GET  /api/studio/skills/<slug>/           — get full skill pack detail
  GET  /api/studio/skills/templates/        — list built-in skill templates
  POST /api/studio/skills/scaffold/         — create a skill pack from UI/JSON payload
  POST /api/studio/skills/validate/         — validate skill packs

  GET  /api/studio/mcp/                     — list MCP server pool
  POST /api/studio/mcp/                     — add MCP server
  GET  /api/studio/mcp/<id>/               — get MCP server
  PUT  /api/studio/mcp/<id>/               — update MCP server
  DELETE /api/studio/mcp/<id>/             — delete MCP server
  POST /api/studio/mcp/<id>/test/          — test MCP connection
  GET  /api/studio/mcp/<id>/tools/         — inspect MCP tools
  GET  /api/studio/mcp/templates/           — list MCP templates

  GET  /api/studio/triggers/               — list triggers
  POST /api/studio/triggers/               — create trigger
  PUT  /api/studio/triggers/<id>/          — update trigger
  DELETE /api/studio/triggers/<id>/        — delete trigger
  POST /api/studio/triggers/<token>/receive/ — webhook endpoint (csrf_exempt)

  GET  /api/studio/templates/              — list pipeline templates
  POST /api/studio/templates/<slug>/use/   — instantiate template

  GET  /api/studio/servers/               — list accessible servers (for node config)
"""

import asyncio
import contextlib
import json
import os
import shutil
import threading
from pathlib import Path, PurePosixPath

from django.contrib.auth.models import User
from django.conf import settings as django_settings
from django.db.models import Q
from core_ui.access import feature_allowed_for_user
from core_ui.decorators import require_any_feature, require_feature
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from app.runtime_limits import get_pipeline_run_limit_error
from core_ui.managed_secrets import get_mcp_secret_env, get_mcp_secret_env_keys
from .mcp_client import MCPClientError, inspect_mcp_server
from .models import (
    AgentConfig,
    MCPServerPool,
    Pipeline,
    PipelineRun,
    PipelineTemplate,
    PipelineTrigger,
    StudioSkillAccess,
)
from .pipeline_runtime import get_executor_for_run, update_runtime_control
from .pipeline_validation import ensure_json_object, validate_pipeline_definition
from .skill_authoring import parse_csv_items, scaffold_skill, validate_skill_dir, validate_skills
from .skill_policy import compile_skill_policies
from .skill_registry import SkillNotFoundError, get_skill, list_skills, normalise_skill_slugs, resolve_skills
from .skill_templates import get_skill_template, list_skill_templates

# ---------------------------------------------------------------------------
# Notification config helpers  (stored in BASE_DIR/.notification_config.json)
# ---------------------------------------------------------------------------

_NOTIF_CONFIG_PATH = Path(getattr(django_settings, "BASE_DIR", ".")) / ".notification_config.json"

_NOTIF_DEFAULTS = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "notify_email": "",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "from_email": "",
    "site_url": "",
}


def _load_notif_config() -> dict:
    """Read notification config from file; fall back to Django / env defaults."""
    base: dict = {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "") or getattr(django_settings, "TELEGRAM_BOT_TOKEN", "") or "",
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "") or getattr(django_settings, "TELEGRAM_CHAT_ID", "") or "",
        "notify_email": (
            os.getenv("PIPELINE_NOTIFY_EMAIL", "")
            or getattr(django_settings, "PIPELINE_NOTIFY_EMAIL", "")
            or os.getenv("EMAIL_HOST_USER", "")
            or getattr(django_settings, "EMAIL_HOST_USER", "")
            or ""
        ),
        "smtp_host": getattr(django_settings, "EMAIL_HOST", "smtp.gmail.com") or "",
        "smtp_port": str(getattr(django_settings, "EMAIL_PORT", 587)),
        "smtp_user": getattr(django_settings, "EMAIL_HOST_USER", "") or "",
        "smtp_password": getattr(django_settings, "EMAIL_HOST_PASSWORD", "") or "",
        "from_email": getattr(django_settings, "DEFAULT_FROM_EMAIL", "") or "",
        "site_url": getattr(django_settings, "SITE_URL", "http://localhost:8000") or "http://localhost:8000",
    }
    if _NOTIF_CONFIG_PATH.exists():
        try:
            saved = json.loads(_NOTIF_CONFIG_PATH.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if k in base and v:  # only override with non-empty saved values
                    base[k] = v
        except Exception:
            pass
    return base


def _save_notif_config(data: dict):
    """Persist notification config (only non-empty values)."""
    existing = {}
    if _NOTIF_CONFIG_PATH.exists():
        with contextlib.suppress(Exception):
            existing = json.loads(_NOTIF_CONFIG_PATH.read_text(encoding="utf-8"))
    for k in _NOTIF_DEFAULTS:
        if k in data:
            existing[k] = data[k]
    _NOTIF_CONFIG_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def _resolve_from_email_smtp(from_email: str, smtp_user: str, smtp_host: str) -> str:
    """Use real mailbox as From when default is noreply@weuai.site or broken like noreply@login."""
    if not from_email or "weuai.site" in from_email or "noreply@" in (from_email or "").lower():
        if not smtp_user:
            return from_email or "pipeline@noreply.local"
        user = (smtp_user or "").strip()
        if "@" in user:
            return user
        host = (smtp_host or "").lower()
        if "yandex" in host:
            return f"{user}@yandex.ru"
        if "gmail" in host:
            return f"{user}@gmail.com"
        return user
    return from_email


def _normalize_email_recipient(to_email: str, smtp_host: str) -> str:
    """If recipient is only login (no @), append domain for Yandex/Gmail."""
    to_email = (to_email or "").strip()
    if not to_email or "@" in to_email:
        return to_email
    host = (smtp_host or "").lower()
    if "yandex" in host:
        return f"{to_email}@yandex.ru"
    if "gmail" in host:
        return f"{to_email}@gmail.com"
    return to_email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _validation_err(errors: list[str], *, prefix: str = "Validation failed") -> JsonResponse:
    message = f"{prefix}: {'; '.join(errors)}"
    return JsonResponse({"error": message, "details": errors}, status=400)


def _require_admin(request, *, message: str = "Admin access required") -> JsonResponse | None:
    if getattr(request.user, "is_staff", False):
        return None
    return _err(message, 403)


STUDIO_FEATURE_PIPELINES = "studio_pipelines"
STUDIO_FEATURE_RUNS = "studio_runs"
STUDIO_FEATURE_AGENTS = "studio_agents"
STUDIO_FEATURE_SKILLS = "studio_skills"
STUDIO_FEATURE_MCP = "studio_mcp"
STUDIO_FEATURE_NOTIFICATIONS = "studio_notifications"


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _user_has_feature(user, feature: str) -> bool:
    return feature_allowed_for_user(user, feature)


def _owner_payload(owner: User | None) -> dict | None:
    if owner is None:
        return None
    return {"id": owner.id, "username": owner.username}


def _shared_user_payloads(shared_users) -> list[dict]:
    return [{"id": user.id, "username": user.username} for user in shared_users]


def _access_mode(*, owner_id: int | None, viewer) -> str:
    if _is_admin(viewer) and owner_id and owner_id != viewer.id:
        return "admin"
    if owner_id and viewer and owner_id == viewer.id:
        return "owner"
    return "shared"


def _pipeline_queryset_for_user(user):
    qs = Pipeline.objects.select_related("owner")
    if _is_admin(user):
        return qs.order_by("-updated_at")
    return qs.filter(owner=user).order_by("-updated_at")


def _run_queryset_for_user(user):
    qs = PipelineRun.objects.select_related("pipeline", "pipeline__owner", "triggered_by")
    if _is_admin(user):
        return qs.order_by("-created_at")
    return qs.filter(pipeline__owner=user).order_by("-created_at")


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


def _mcp_read_queryset_for_user(user):
    qs = MCPServerPool.objects.select_related("owner").prefetch_related("shared_with")
    if _is_admin(user):
        return qs.order_by("name")
    return qs.filter(Q(owner=user) | Q(is_shared=True) | Q(shared_with=user)).distinct().order_by("name")


def _mcp_write_queryset_for_user(user):
    qs = MCPServerPool.objects.select_related("owner").prefetch_related("shared_with")
    if _is_admin(user):
        return qs
    return qs.filter(owner=user)


def _skill_access_map(slugs: list[str]) -> dict[str, StudioSkillAccess]:
    if not slugs:
        return {}
    rows = (
        StudioSkillAccess.objects.filter(slug__in=slugs)
        .select_related("owner")
        .prefetch_related("shared_with")
    )
    return {row.slug.lower(): row for row in rows}


def _get_skill_access(slug: str) -> StudioSkillAccess | None:
    return (
        StudioSkillAccess.objects.filter(slug=slug)
        .select_related("owner")
        .prefetch_related("shared_with")
        .first()
    )


def _ensure_skill_access(slug: str, owner: User | None = None) -> StudioSkillAccess:
    access, _created = StudioSkillAccess.objects.get_or_create(slug=slug, defaults={"owner": owner})
    if owner is not None and access.owner_id is None:
        access.owner = owner
        access.save()
    return (
        StudioSkillAccess.objects.filter(pk=access.pk)
        .select_related("owner")
        .prefetch_related("shared_with")
        .get()
    )


def _can_read_skill(user, access: StudioSkillAccess | None) -> bool:
    if _is_admin(user):
        return True
    if access is None or not user or not getattr(user, "is_authenticated", False):
        return False
    if access.owner_id == user.id or access.is_shared:
        return True
    return any(shared_user.id == user.id for shared_user in access.shared_with.all())


def _can_edit_skill(user, access: StudioSkillAccess | None) -> bool:
    if _is_admin(user):
        return True
    return bool(access and user and getattr(user, "is_authenticated", False) and access.owner_id == user.id)


def _apply_shared_users(instance, shared_user_ids: list[int]):
    if instance.owner_id:
        shared_user_ids = [user_id for user_id in shared_user_ids if user_id != instance.owner_id]
    users = User.objects.filter(id__in=shared_user_ids, is_active=True).order_by("username")
    instance.shared_with.set(users)


def _skill_to_summary_dict(skill, viewer, access: StudioSkillAccess | None) -> dict:
    shared_users = _shared_user_payloads(access.shared_with.all()) if access else []
    data = skill.to_summary_dict()
    data.update(
        {
            "path": skill.path,
            "owner": _owner_payload(access.owner) if access else None,
            "owner_username": access.owner.username if access and access.owner_id else "",
            "is_owner": bool(access and access.owner_id == getattr(viewer, "id", None)),
            "can_edit": _can_edit_skill(viewer, access),
            "can_share": _is_admin(viewer),
            "is_shared": bool(access and (access.is_shared or shared_users)),
            "shared_user_ids": [item["id"] for item in shared_users],
            "shared_users": shared_users,
            "access_mode": _access_mode(owner_id=access.owner_id if access else None, viewer=viewer),
        }
    )
    return data


def _skill_to_detail_dict(skill, viewer, access: StudioSkillAccess | None) -> dict:
    data = skill.to_detail_dict()
    data.update(_skill_to_summary_dict(skill, viewer, access))
    return data


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


def _mcp_to_dict(mcp: MCPServerPool, viewer) -> dict:
    can_edit = _is_admin(viewer) or mcp.owner_id == getattr(viewer, "id", None)
    shared_users = _shared_user_payloads(mcp.shared_with.all())
    return {
        "id": mcp.pk,
        "name": mcp.name,
        "description": mcp.description,
        "transport": mcp.transport,
        "command": mcp.command,
        "args": mcp.args,
        "env": mcp.env if can_edit else {},
        "secret_env_keys": get_mcp_secret_env_keys(mcp.id) if can_edit else [],
        "url": mcp.url,
        "is_shared": bool(mcp.is_shared or shared_users),
        "shared_user_ids": [item["id"] for item in shared_users],
        "shared_users": shared_users,
        "owner": _owner_payload(mcp.owner),
        "owner_username": mcp.owner.username,
        "is_owner": mcp.owner_id == getattr(viewer, "id", None),
        "can_edit": can_edit,
        "can_share": _is_admin(viewer),
        "access_mode": _access_mode(owner_id=mcp.owner_id, viewer=viewer),
        "last_test_ok": mcp.last_test_ok,
        "last_test_at": mcp.last_test_at.isoformat() if mcp.last_test_at else None,
        "last_test_error": mcp.last_test_error,
    }


def _extract_json_object(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    if not text:
        return {}
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _compact_node_summary(node: dict) -> dict:
    data = node.get("data") if isinstance(node, dict) else {}
    if not isinstance(data, dict):
        data = {}
    label = str(data.get("label") or "").strip()
    return {
        "id": str(node.get("id") or ""),
        "type": str(node.get("type") or ""),
        "label": label or None,
    }


def _compact_selected_node(node: dict) -> dict:
    data = node.get("data") if isinstance(node, dict) else {}
    if not isinstance(data, dict):
        data = {}
    return {
        "id": str(node.get("id") or ""),
        "type": str(node.get("type") or ""),
        "position": node.get("position") or {},
        "data": data,
    }


def _sanitize_graph_patch(raw_graph_patch: object, *, fallback_anchor: str | None = None) -> dict:
    if not isinstance(raw_graph_patch, dict):
        return {"anchor_node_id": fallback_anchor, "nodes": [], "edges": []}

    raw_nodes = raw_graph_patch.get("nodes")
    raw_edges = raw_graph_patch.get("edges")
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes = []
    for item in raw_nodes[:24]:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or "").strip()
        node_type = str(item.get("type") or "").strip()
        if not ref or not node_type:
            continue
        raw_data = item.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        label = str(item.get("label") or "").strip()
        try:
            x_offset = float(item["x_offset"]) if item.get("x_offset") not in (None, "") else None
        except (TypeError, ValueError):
            x_offset = None
        try:
            y_offset = float(item["y_offset"]) if item.get("y_offset") not in (None, "") else None
        except (TypeError, ValueError):
            y_offset = None
        nodes.append(
            {
                "ref": ref,
                "type": node_type,
                "data": data,
                "label": label or None,
                "x_offset": x_offset,
                "y_offset": y_offset,
            }
        )

    edges = []
    for item in raw_edges[:48]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target:
            continue
        edges.append(
            {
                "source": source,
                "target": target,
                "label": str(item.get("label") or "").strip() or None,
                "source_handle": str(item.get("source_handle") or "").strip() or None,
                "target_handle": str(item.get("target_handle") or "").strip() or None,
            }
        )

    anchor_node_id = str(raw_graph_patch.get("anchor_node_id") or "").strip() or fallback_anchor
    return {
        "anchor_node_id": anchor_node_id,
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipelines(request):
    if request.method == "GET":
        qs = _pipeline_queryset_for_user(request.user)
        search = request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(name__icontains=search)
        return _ok([p.to_list_dict() for p in qs])

    if request.method == "POST":
        data = _json_body(request)
        name = data.get("name", "").strip()
        if not name:
            return _err("name is required")
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        errors = validate_pipeline_definition(nodes=nodes, edges=edges, owner=request.user)
        if errors:
            return _validation_err(errors, prefix="Pipeline validation failed")
        pipeline = Pipeline.objects.create(
            name=name,
            description=data.get("description", ""),
            icon=data.get("icon", "⚡"),
            tags=data.get("tags", []),
            nodes=nodes,
            edges=edges,
            owner=request.user,
        )
        pipeline.sync_triggers_from_nodes()
        return _ok(pipeline.to_detail_dict(), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_detail(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)

    if request.method == "GET":
        return _ok(pipeline.to_detail_dict())

    if request.method == "PUT":
        data = _json_body(request)
        next_nodes = data.get("nodes", pipeline.nodes)
        next_edges = data.get("edges", pipeline.edges)
        errors = validate_pipeline_definition(nodes=next_nodes, edges=next_edges, owner=pipeline.owner)
        if errors:
            return _validation_err(errors, prefix="Pipeline validation failed")
        for field in ("name", "description", "icon", "tags", "nodes", "edges", "is_shared"):
            if field in data:
                setattr(pipeline, field, data[field])
        pipeline.save()
        pipeline.sync_triggers_from_nodes()
        return _ok(pipeline.to_detail_dict())

    if request.method == "DELETE":
        pipeline.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_run(request, pipeline_id: int):
    """Trigger a manual pipeline run."""
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)

    limit_error = get_pipeline_run_limit_error(pipeline.owner)
    if limit_error:
        return JsonResponse(limit_error, status=429)

    payload = _json_body(request)
    context, error = ensure_json_object(payload.get("context", {}), label="context")
    if error:
        return _err(error)

    validation_errors = validate_pipeline_definition(nodes=pipeline.nodes, edges=pipeline.edges, owner=pipeline.owner)
    if validation_errors:
        return _validation_err(validation_errors, prefix="Pipeline is not runnable")

    run = PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=request.user,
        status=PipelineRun.STATUS_PENDING,
        context=context,
        trigger_data={"source": "manual"},
    )
    _launch_pipeline_run_async(run)
    return _ok(run.to_dict(), status=202)


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_clone(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)

    clone = Pipeline.objects.create(
        name=f"{pipeline.name} (copy)",
        description=pipeline.description,
        icon=pipeline.icon,
        tags=pipeline.tags,
        nodes=pipeline.nodes,
        edges=pipeline.edges,
        owner=request.user,
    )
    clone.sync_triggers_from_nodes()
    return _ok(clone.to_detail_dict(), status=201)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_pipeline_runs(request, pipeline_id: int):
    pipeline = _get_pipeline(request, pipeline_id)
    if pipeline is None:
        return _err("Pipeline not found", 404)
    runs = pipeline.runs.order_by("-created_at")[:50]
    return _ok([r.to_dict() for r in runs])


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_assistant(request):
    data = _json_body(request)
    user_message = str(data.get("user_message") or "").strip()
    pipeline_name = str(data.get("pipeline_name") or "").strip() or "Untitled pipeline"
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    selected_node = data.get("selected_node")

    if not user_message:
        return _err("user_message is required")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return _err("nodes and edges must be arrays")
    if selected_node not in (None, "") and not isinstance(selected_node, dict):
        return _err("selected_node must be an object or null")

    pipeline_id_raw = data.get("pipeline_id")
    if pipeline_id_raw not in (None, ""):
        try:
            pipeline_id = int(pipeline_id_raw)
        except (TypeError, ValueError):
            return _err("pipeline_id must be an integer")
        if _get_pipeline(request, pipeline_id) is None:
            return _err("Pipeline not found", 404)

    selected_node_id = str((selected_node or {}).get("id") or "").strip()

    node_map = {
        str(item.get("id") or ""): item
        for item in nodes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if selected_node_id and selected_node_id not in node_map:
        node_map[selected_node_id] = selected_node
    current_node = node_map[selected_node_id] if selected_node_id and selected_node_id in node_map else None

    if current_node:
        incoming_ids = [
            str(edge.get("source") or "")
            for edge in edges
            if isinstance(edge, dict) and str(edge.get("target") or "") == selected_node_id
        ]
        outgoing_ids = [
            str(edge.get("target") or "")
            for edge in edges
            if isinstance(edge, dict) and str(edge.get("source") or "") == selected_node_id
        ]
        incoming_nodes = [_compact_node_summary(node_map[node_id]) for node_id in incoming_ids if node_id in node_map]
        outgoing_nodes = [_compact_node_summary(node_map[node_id]) for node_id in outgoing_ids if node_id in node_map]
    else:
        incoming_nodes = []
        outgoing_nodes = []

    agents = []
    if _user_has_feature(request.user, STUDIO_FEATURE_AGENTS):
        agents = [
            {
                "id": agent.pk,
                "name": agent.name,
                "description": agent.description,
                "mcp_server_ids": list(agent.mcp_servers.values_list("id", flat=True)),
                "skill_slugs": list(agent.skill_slugs or []),
                "server_scope_ids": list(agent.server_scope.values_list("id", flat=True)),
            }
            for agent in _agent_read_queryset_for_user(request.user).order_by("name")
        ]
    mcps = []
    if _user_has_feature(request.user, STUDIO_FEATURE_MCP):
        mcps = [
            {
                "id": mcp.pk,
                "name": mcp.name,
                "description": mcp.description,
                "transport": mcp.transport,
                "last_test_ok": mcp.last_test_ok,
            }
            for mcp in _mcp_read_queryset_for_user(request.user)
        ]

    from servers.models import Server

    servers = [
        {
            "id": server.pk,
            "name": server.name,
            "host": server.host,
        }
        for server in Server.objects.filter(user=request.user).order_by("name")
    ]
    available_skills = []
    if _user_has_feature(request.user, STUDIO_FEATURE_SKILLS):
        all_skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in all_skills])
        available_skills = [
            _skill_to_summary_dict(skill, request.user, access_map.get(skill.slug.lower()))
            for skill in all_skills
            if _can_read_skill(request.user, access_map.get(skill.slug.lower()))
        ]

    selected_data = current_node.get("data") if current_node and isinstance(current_node.get("data"), dict) else {}
    selected_skill_slugs = normalise_skill_slugs(selected_data.get("skill_slugs"))
    selected_skill_details = []
    for slug in selected_skill_slugs:
        try:
            skill = get_skill(slug)
        except SkillNotFoundError:
            continue
        selected_skill_details.append(
            {
                "slug": skill.slug,
                "name": skill.name,
                "guardrail_summary": list(skill.guardrail_summary),
                "runtime_policy": skill.runtime_policy,
                "content": skill.content[:5000],
            }
        )

    selected_mcp_tools = []
    selected_mcp_id_raw = selected_data.get("mcp_server_id")
    try:
        selected_mcp_id = int(selected_mcp_id_raw) if selected_mcp_id_raw not in (None, "") else None
    except (TypeError, ValueError):
        selected_mcp_id = None

    if selected_mcp_id:
        try:
            selected_mcp = _mcp_read_queryset_for_user(request.user).get(pk=selected_mcp_id)
            inspection = asyncio.run(inspect_mcp_server(selected_mcp))
            selected_mcp_tools = [
                {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema") or {},
                }
                for tool in inspection.get("tools", [])[:30]
                if isinstance(tool, dict)
            ]
        except Exception:
            selected_mcp_tools = []

    prompt = f"""Ты — корпоративный AI copilot для Studio Pipeline Editor.

Ты помогаешь администратору проектировать, проверять и улучшать ВЕСЬ pipeline. Если передана focus node, ты можешь также дать точечный patch для неё.

Правила:
- Смотри на весь граф, а не только на одну ноду.
- Предлагай изменения с учетом реальных доступных ресурсов: servers, agent configs, MCP servers, skills.
- Если можно использовать существующий ресурс, ссылайся на него по точному ID.
- Если нужен точечный конфиг ноды, указывай target_node_id и заполняй node_patch только полями data этой ноды.
- Если хочешь предложить новые шаги или ветку, используй graph_patch.
- Если вопрос общий по pipeline, можешь оставить target_node_id пустым и дать только graph_patch и reply.
- Не удаляй существующие значения без явной просьбы пользователя.
- Для logic/condition обязательно учитывай source_node_id и входящие связи.
- Для agent/mcp_call предпочитай доступные MCP tools и валидные JSON arguments.
- reply должен быть понятным оператору: что уже хорошо, что отсутствует, что нужно добавить или изменить дальше.

Верни ТОЛЬКО JSON-объект строго такого вида:
{{
  "reply": "Markdown explanation for the operator",
  "target_node_id": null,
  "node_patch": {{}},
  "graph_patch": {{
    "anchor_node_id": null,
    "nodes": [
      {{
        "ref": "new_step_1",
        "type": "agent/llm_query",
        "label": "Optional human label",
        "data": {{}},
        "x_offset": 260,
        "y_offset": 0
      }}
    ],
    "edges": [
      {{
        "source": "existing_node_id_or_ref",
        "target": "existing_node_id_or_ref",
        "label": ""
      }}
    ]
  }},
  "warnings": ["optional warning"]
}}

Правила для graph_patch:
- graph_patch должен содержать только НОВЫЕ ноды и новые связи.
- В nodes[].ref используй короткие уникальные временные идентификаторы.
- В edges[].source / edges[].target можно ссылаться либо на существующий node_id, либо на ref из graph_patch.nodes.
- Если нужны только текстовые рекомендации без вставки в graph, оставляй graph_patch.nodes и graph_patch.edges пустыми.
- Используй только допустимые типы нод:
  trigger/manual, trigger/webhook, trigger/schedule,
  agent/react, agent/multi, agent/ssh_cmd, agent/llm_query, agent/mcp_call,
  logic/condition, logic/parallel, logic/wait, logic/human_approval,
  output/report, output/webhook, output/email, output/telegram

Контекст пайплайна:
{json.dumps({
    "pipeline_name": pipeline_name,
    "focus_node": _compact_selected_node(current_node) if current_node else None,
    "incoming_nodes": incoming_nodes,
    "outgoing_nodes": outgoing_nodes,
    "graph_nodes": [_compact_node_summary(item) for item in node_map.values()],
    "available_agents": agents,
    "available_servers": servers,
    "available_mcp_servers": mcps,
    "selected_mcp_tools": selected_mcp_tools,
    "available_skills": available_skills,
    "selected_skill_details": selected_skill_details,
}, ensure_ascii=False, indent=2)}

Вопрос пользователя:
{user_message}
"""

    async def _call() -> str:
        from app.core.llm import LLMProvider

        provider = LLMProvider()
        chunks = []
        async for chunk in provider.stream_chat(prompt, model="auto", purpose="chat"):
            chunks.append(chunk)
        return "".join(chunks)

    loop = asyncio.new_event_loop()
    try:
        raw_response = loop.run_until_complete(_call())
    except Exception as exc:
        return _err(f"LLM error: {exc}", 500)
    finally:
        loop.close()

    parsed = _extract_json_object(raw_response)
    reply = str(parsed.get("reply") or "").strip() or raw_response.strip() or "No assistant response."
    target_node_id = str(parsed.get("target_node_id") or "").strip() or None
    node_patch = parsed.get("node_patch")
    if not isinstance(node_patch, dict):
        node_patch = {}
    graph_patch = _sanitize_graph_patch(parsed.get("graph_patch"), fallback_anchor=target_node_id)
    warnings = parsed.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    return _ok(
        {
            "reply": reply,
            "target_node_id": target_node_id,
            "node_patch": node_patch,
            "graph_patch": graph_patch,
            "warnings": [str(item) for item in warnings if str(item).strip()][:8],
        }
    )


def _get_pipeline(request, pipeline_id: int) -> Pipeline | None:
    return _pipeline_queryset_for_user(request.user).filter(pk=pipeline_id).first()


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@require_feature(STUDIO_FEATURE_RUNS)
def api_runs(request):
    qs = _run_queryset_for_user(request.user)[:100]
    return _ok([r.to_dict() for r in qs])


@require_feature(STUDIO_FEATURE_RUNS)
def api_run_detail(request, run_id: int):
    run = _run_queryset_for_user(request.user).filter(pk=run_id).first()
    if run is None:
        return _err("Run not found", 404)
    return _ok(run.to_dict())


@require_feature(STUDIO_FEATURE_RUNS)
@require_http_methods(["POST"])
def api_run_stop(request, run_id: int):
    run = _run_queryset_for_user(request.user).filter(pk=run_id).first()
    if run is None:
        return _err("Run not found", 404)

    executor = get_executor_for_run(run.id)
    control, stop_delivered = update_runtime_control(run, live_executor=executor, stop_requested=True)

    if run.status in {PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING}:
        run.status = PipelineRun.STATUS_STOPPED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
    return _ok({"ok": True, "live_executor": stop_delivered, "runtime_control": control})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_run_approve(request, run_id: int, node_id: str):
    """
    Public endpoint — authenticated only by the one-time token embedded in the URL.

    Approve:  GET /api/studio/runs/<id>/approve/<node_id>/?token=...&decision=approved
    Reject:   GET /api/studio/runs/<id>/approve/<node_id>/?token=...&decision=rejected
    Respond:  POST with JSON {"token": "...", "decision": "approved", "response_text": "..."}

    The human_approval node polls the DB for `approval_decision` to appear.
    """
    # Accept token/decision from query string (GET link in email) or JSON body (POST from bot)
    if request.method == "GET":
        token = request.GET.get("token", "")
        decision = request.GET.get("decision", "")
        response_text = request.GET.get("response", "")
    else:
        body = _json_body(request)
        token = body.get("token", "")
        decision = body.get("decision", "")
        response_text = body.get("response_text", "")

    if not token:
        return _err("token is required", 400)
    if decision not in ("approved", "rejected"):
        return _err("decision must be 'approved' or 'rejected'", 400)

    try:
        run = PipelineRun.objects.get(pk=run_id)
    except PipelineRun.DoesNotExist:
        return _err("Run not found", 404)

    node_state = run.node_states.get(node_id)
    if not node_state:
        return _err(f"Node '{node_id}' not found in run #{run_id}", 404)

    stored_token = node_state.get("approval_token", "")
    if not stored_token or stored_token != token:
        return _err("Invalid or expired token", 403)

    if node_state.get("approval_decision"):
        existing = node_state["approval_decision"]
        return _ok({"ok": True, "message": f"Already decided: {existing}"})

    # Record the decision — the polling loop in the executor will pick this up
    run.node_states[node_id] = {
        **node_state,
        "approval_decision": decision,
        "approval_response": response_text,
        "decided_at": timezone.now().isoformat(),
    }
    PipelineRun.objects.filter(pk=run_id).update(node_states=run.node_states)

    emoji = "✅" if decision == "approved" else "❌"
    html = (
        f"<html><body style='font-family:sans-serif;max-width:600px;margin:60px auto;text-align:center'>"
        f"<h1>{emoji} {decision.capitalize()}</h1>"
        f"<p>Your decision for pipeline <strong>{run.pipeline.name}</strong> (run #{run_id}) "
        f"has been recorded.</p>"
        f"<p style='color:#888'>You can close this tab.</p>"
        f"</body></html>"
    )
    from django.http import HttpResponse

    return HttpResponse(html, content_type="text/html")


# ---------------------------------------------------------------------------
# Agent Configs
# ---------------------------------------------------------------------------


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
            skill_slugs=_sanitize_accessible_skill_slugs(
                request.user,
                _normalise_skill_payload(data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")),
            ),
            owner=request.user,
        )
        _set_accessible_mcp_servers(agent, request.user, requested_mcp_ids)
        _set_owned_server_scope(
            agent,
            request.user,
            _normalise_related_ids(data.get("server_scope_ids") if "server_scope_ids" in data else data.get("server_scope")),
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
                _normalise_related_ids(data.get("server_scope_ids") if "server_scope_ids" in data else data.get("server_scope")),
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


def _set_accessible_mcp_servers(agent: AgentConfig, user, ids: list[int] | None):
    if not _user_has_feature(user, STUDIO_FEATURE_MCP):
        agent.mcp_servers.set([])
        return
    requested_ids = ids or []
    items = list(_mcp_read_queryset_for_user(user).filter(pk__in=requested_ids))
    agent.mcp_servers.set(items)


def _set_owned_server_scope(agent: AgentConfig, owner, ids: list[int] | None):
    from servers.models import Server

    requested_ids = ids or []
    items = list(Server.objects.filter(pk__in=requested_ids, user=owner))
    agent.server_scope.set(items)


def _normalise_related_ids(raw_values) -> list[int]:
    if raw_values is None or not isinstance(raw_values, list):
        return []

    ids: list[int] = []
    for item in raw_values:
        value = item.get("id") if isinstance(item, dict) else item
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _normalise_skill_payload(raw_values) -> list[str]:
    return normalise_skill_slugs(raw_values)


def _sanitize_accessible_skill_slugs(user, slugs: list[str]) -> list[str]:
    if not slugs or not _user_has_feature(user, STUDIO_FEATURE_SKILLS):
        return []

    access_map = _skill_access_map(slugs)
    sanitized: list[str] = []
    for slug in slugs:
        skill = None
        with contextlib.suppress(SkillNotFoundError):
            skill = get_skill(slug)
        if skill is None:
            continue
        access = access_map.get(skill.slug.lower())
        if _is_admin(user) or _can_read_skill(user, access):
            sanitized.append(skill.slug)
    return sanitized


def _normalise_string_list(raw_values) -> list[str]:
    return parse_csv_items(raw_values)


_SKILL_WORKSPACE_TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".csv",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".js",
    ".ts",
}
_SKILL_WORKSPACE_DIRS = {"references", "scripts", "assets"}
_SKILL_WORKSPACE_MAX_BYTES = 500_000


def _skill_dir_from_slug(slug: str) -> Path:
    skill = get_skill(slug)
    return Path(skill.path).resolve().parent


def _skill_workspace_kind(path: str) -> str:
    if path == "SKILL.md":
        return "skill"
    if path.startswith("references/"):
        return "reference"
    if path.startswith("scripts/"):
        return "script"
    if path.startswith("assets/"):
        return "asset"
    return "file"


def _skill_workspace_language(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".md"):
        return "markdown"
    if lowered.endswith((".yml", ".yaml")):
        return "yaml"
    if lowered.endswith(".json"):
        return "json"
    if lowered.endswith(".py"):
        return "python"
    if lowered.endswith((".sh", ".bash", ".zsh")):
        return "shell"
    if lowered.endswith(".ts"):
        return "typescript"
    if lowered.endswith(".js"):
        return "javascript"
    if lowered.endswith(".sql"):
        return "sql"
    if lowered.endswith(".csv"):
        return "csv"
    return "text"


def _normalise_skill_workspace_path(raw_path: str) -> tuple[str | None, str | None]:
    candidate = str(raw_path or "").strip().replace("\\", "/")
    if not candidate:
        return None, "path is required"
    pure = PurePosixPath(candidate)
    if pure.is_absolute():
        return None, "absolute paths are not allowed"
    parts = [part for part in pure.parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None, "invalid path"
    if any(part.startswith(".") for part in parts):
        return None, "hidden paths are not allowed"
    if parts == ["SKILL.md"]:
        return "SKILL.md", None
    if parts[0] not in _SKILL_WORKSPACE_DIRS:
        return None, "path must live under references/, scripts/, or assets/"
    if len(parts) < 2:
        return None, "file name is required"
    filename = parts[-1]
    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in _SKILL_WORKSPACE_TEXT_EXTENSIONS:
        return None, f"unsupported file type: {suffix}"
    return "/".join(parts), None


def _resolve_skill_workspace_file(skill_dir: Path, raw_path: str) -> tuple[Path | None, str | None, str | None]:
    normalized, error = _normalise_skill_workspace_path(raw_path)
    if error:
        return None, None, error
    file_path = (skill_dir / normalized).resolve()
    try:
        file_path.relative_to(skill_dir)
    except ValueError:
        return None, None, "path escapes the skill directory"
    return file_path, normalized, None


def _skill_workspace_file_payload(
    skill_dir: Path,
    relative_path: str,
    *,
    include_content: bool = False,
    editable: bool = True,
) -> dict:
    file_path = (skill_dir / relative_path).resolve()
    payload = {
        "path": relative_path,
        "name": file_path.name,
        "kind": _skill_workspace_kind(relative_path),
        "language": _skill_workspace_language(relative_path),
        "size": file_path.stat().st_size if file_path.exists() else 0,
        "editable": bool(editable),
    }
    if include_content:
        try:
            payload["content"] = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Only UTF-8 text files can be edited in the web workspace: {relative_path}") from exc
    return payload


def _list_skill_workspace_files(skill_dir: Path, *, editable: bool = True) -> list[dict]:
    files: list[dict] = []
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        files.append(_skill_workspace_file_payload(skill_dir, "SKILL.md", editable=editable))
    for folder in ("references", "scripts", "assets"):
        folder_path = skill_dir / folder
        if not folder_path.exists() or not folder_path.is_dir():
            continue
        for file_path in sorted(folder_path.rglob("*"), key=lambda item: str(item).lower()):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(skill_dir).as_posix()
            try:
                files.append(_skill_workspace_file_payload(skill_dir, relative_path, editable=editable))
            except ValueError:
                continue
    return files


def _skill_workspace_response(slug: str, viewer, access: StudioSkillAccess | None) -> dict:
    skill = get_skill(slug)
    skill_dir = Path(skill.path).resolve().parent
    validation = validate_skill_dir(skill_dir)
    can_edit = _can_edit_skill(viewer, access)
    return {
        "skill": _skill_to_detail_dict(skill, viewer, access),
        "files": _list_skill_workspace_files(skill_dir, editable=can_edit),
        "validation": validation.to_dict(),
    }


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET"])
def api_skills(request):
    skills = list_skills()
    access_map = _skill_access_map([skill.slug for skill in skills])
    visible = []
    for skill in skills:
        access = access_map.get(skill.slug.lower())
        if not _can_read_skill(request.user, access):
            continue
        visible.append(_skill_to_summary_dict(skill, request.user, access))
    return _ok(visible)


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET", "PUT"])
def api_skill_detail(request, slug: str):
    try:
        skill = get_skill(slug)
    except SkillNotFoundError:
        return _err("Skill not found", 404)
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(request.user, access):
        return _err("Skill not found", 404)

    if request.method == "GET":
        return _ok(_skill_to_detail_dict(skill, request.user, access))

    admin_error = _require_admin(request, message="Only admin can change skill sharing")
    if admin_error:
        return admin_error
    data = _json_body(request)
    access = _ensure_skill_access(skill.slug, owner=access.owner if access else None)
    if "is_shared" in data:
        access.is_shared = bool(data.get("is_shared"))
        access.save(update_fields=["is_shared"])
    if "shared_user_ids" in data:
        _apply_shared_users(access, _normalise_related_ids(data.get("shared_user_ids")))
    access = _get_skill_access(skill.slug)
    return _ok(_skill_to_detail_dict(skill, request.user, access))


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET"])
def api_skill_templates(_request):
    return _ok([item.to_dict() for item in list_skill_templates()])


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["POST"])
def api_skill_scaffold(request):
    data = _json_body(request)
    template_slug = str(data.get("template_slug") or "").strip()
    template = get_skill_template(template_slug) if template_slug else None
    if template_slug and template is None:
        return _err("Unknown skill template")

    defaults = dict(template.defaults) if template else {}
    name = str(data.get("name") or defaults.get("name") or "").strip()
    description = str(data.get("description") or defaults.get("description") or "").strip()
    if not name:
        return _err("name is required")
    if not description:
        return _err("description is required")

    raw_runtime_policy = data.get("runtime_policy")
    if raw_runtime_policy not in (None, "") and not isinstance(raw_runtime_policy, dict):
        return _err("runtime_policy must be a JSON object")

    runtime_policy = dict(defaults.get("runtime_policy") or {})
    runtime_policy.update(dict(raw_runtime_policy or {}))

    requested_slug = str(data.get("slug") or "").strip()
    if bool(data.get("force")) and not _is_admin(request.user):
        if not requested_slug:
            return _err("force requires an explicit slug for non-admin users")
        existing_access = _get_skill_access(requested_slug)
        existing_skill = None
        with contextlib.suppress(SkillNotFoundError):
            existing_skill = get_skill(requested_slug)
        if existing_skill is not None and not _can_edit_skill(request.user, existing_access):
            return _err("You can overwrite only your own skills", 403)

    try:
        skill_dir = scaffold_skill(
            name=name,
            description=description,
            slug=requested_slug or None,
            service=str(data.get("service") or defaults.get("service") or "").strip(),
            category=str(data.get("category") or defaults.get("category") or "").strip(),
            safety_level=str(data.get("safety_level") or defaults.get("safety_level") or "standard").strip() or "standard",
            ui_hint=str(data.get("ui_hint") or defaults.get("ui_hint") or "").strip(),
            tags=_normalise_string_list(data.get("tags") or defaults.get("tags")),
            guardrail_summary=_normalise_string_list(data.get("guardrail_summary") or defaults.get("guardrail_summary")),
            recommended_tools=_normalise_string_list(data.get("recommended_tools") or defaults.get("recommended_tools")),
            runtime_policy=runtime_policy,
            with_scripts=bool(data.get("with_scripts")),
            with_references=bool(data.get("with_references")),
            with_assets=bool(data.get("with_assets")),
            force=bool(data.get("force")),
        )
    except (ValueError, FileExistsError) as exc:
        return _err(str(exc))

    validation = validate_skill_dir(skill_dir)
    if validation.errors:
        shutil.rmtree(skill_dir, ignore_errors=True)
        return JsonResponse(
            {
                "error": "Skill scaffold did not pass validation",
                "validation": validation.to_dict(),
            },
            status=400,
        )

    try:
        skill = get_skill(skill_dir.name)
    except SkillNotFoundError:
        return _err("Skill was created but could not be loaded", 500)
    access = _ensure_skill_access(skill.slug, owner=request.user)
    if _is_admin(request.user):
        if "is_shared" in data:
            access.is_shared = bool(data.get("is_shared"))
            access.save(update_fields=["is_shared"])
        if "shared_user_ids" in data:
            _apply_shared_users(access, _normalise_related_ids(data.get("shared_user_ids")))
        access = _get_skill_access(skill.slug)

    return _ok(
        {
            "ok": True,
            "skill": _skill_to_detail_dict(skill, request.user, access),
            "validation": validation.to_dict(),
        },
        status=201,
    )


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["POST"])
def api_skill_validate(request):
    data = _json_body(request)
    slugs = _normalise_string_list(data.get("slugs"))
    strict = bool(data.get("strict"))

    if slugs:
        access_map = _skill_access_map(slugs)
        denied = []
        allowed_slugs = []
        for slug in slugs:
            access = access_map.get(slug.lower())
            if _can_read_skill(request.user, access):
                allowed_slugs.append(slug)
            else:
                denied.append(slug)
        if denied:
            return _err(f"Skills not accessible: {', '.join(denied)}", 403)
        results = validate_skills(allowed_slugs) if allowed_slugs else []
    else:
        all_skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in all_skills])
        visible_slugs = [
            skill.slug
            for skill in all_skills
            if _can_read_skill(request.user, access_map.get(skill.slug.lower()))
        ]
        results = validate_skills(visible_slugs) if visible_slugs else []

    if slugs:
        found = {item.slug.lower() for item in results}
        missing = [slug for slug in slugs if slug.lower() not in found]
        if missing:
            return _err(f"Skills not found: {', '.join(missing)}", 404)

    error_count = sum(len(item.errors) for item in results)
    warning_count = sum(len(item.warnings) for item in results)
    return _ok(
        {
            "results": [item.to_dict() for item in results],
            "summary": {
                "skills": len(results),
                "errors": error_count,
                "warnings": warning_count,
                "is_valid": error_count == 0 and (warning_count == 0 if strict else True),
                "strict": strict,
            },
        }
    )


@require_feature(STUDIO_FEATURE_SKILLS)
@require_http_methods(["GET"])
def api_skill_workspace(request, slug: str):
    try:
        skill = get_skill(slug)
    except SkillNotFoundError:
        return _err("Skill not found", 404)
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(request.user, access):
        return _err("Skill not found", 404)
    return _ok(_skill_workspace_response(skill.slug, request.user, access))


@require_feature(STUDIO_FEATURE_SKILLS)
def api_skill_workspace_file(request, slug: str):
    try:
        skill = get_skill(slug)
    except SkillNotFoundError:
        return _err("Skill not found", 404)
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(request.user, access):
        return _err("Skill not found", 404)
    can_edit = _can_edit_skill(request.user, access)
    skill_dir = _skill_dir_from_slug(skill.slug)

    if request.method == "GET":
        raw_path = request.GET.get("path", "")
        file_path, relative_path, error = _resolve_skill_workspace_file(skill_dir, raw_path)
        if error:
            return _err(error)
        if file_path is None or relative_path is None or not file_path.exists():
            return _err("File not found", 404)
        try:
            return _ok(_skill_workspace_file_payload(skill_dir, relative_path, include_content=True, editable=can_edit))
        except ValueError as exc:
            return _err(str(exc), 400)

    if not can_edit:
        return _err("Only the owner or admin can edit this skill workspace", 403)

    data = _json_body(request)
    raw_path = data.get("path", "")
    file_path, relative_path, error = _resolve_skill_workspace_file(skill_dir, raw_path)
    if error:
        return _err(error)
    if file_path is None or relative_path is None:
        return _err("invalid path")

    if request.method == "POST":
        if file_path.exists():
            return _err("File already exists", 409)
        content = str(data.get("content", ""))
        if len(content.encode("utf-8")) > _SKILL_WORKSPACE_MAX_BYTES:
            return _err("File is too large", 400)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return _ok(
            {
                "ok": True,
                "file": _skill_workspace_file_payload(skill_dir, relative_path, include_content=True, editable=True),
                "validation": validate_skill_dir(skill_dir).to_dict(),
            },
            status=201,
        )

    if request.method == "PUT":
        if not file_path.exists():
            return _err("File not found", 404)
        content = str(data.get("content", ""))
        if len(content.encode("utf-8")) > _SKILL_WORKSPACE_MAX_BYTES:
            return _err("File is too large", 400)
        file_path.write_text(content, encoding="utf-8")
        return _ok(
            {
                "ok": True,
                "file": _skill_workspace_file_payload(skill_dir, relative_path, include_content=True, editable=True),
                "validation": validate_skill_dir(skill_dir).to_dict(),
            }
        )

    if request.method == "DELETE":
        if relative_path == "SKILL.md":
            return _err("SKILL.md cannot be deleted", 400)
        if not file_path.exists():
            return _err("File not found", 404)
        file_path.unlink()
        with contextlib.suppress(OSError):
            parent = file_path.parent
            while parent != skill_dir and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        return _ok({"ok": True, "validation": validate_skill_dir(skill_dir).to_dict()})

    return _err("Method not allowed", 405)


# ---------------------------------------------------------------------------
# MCP Server Pool
# ---------------------------------------------------------------------------

KEYCLOAK_TEMPLATE_URL = os.getenv("STUDIO_KEYCLOAK_MCP_URL", "http://127.0.0.1:8766/mcp")


MCP_TEMPLATES = [
    {
        "slug": "github",
        "name": "GitHub",
        "description": "GitHub repository management via MCP",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        "icon": "🐙",
    },
    {
        "slug": "filesystem",
        "name": "Filesystem",
        "description": "Read/write local filesystem via MCP",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed"],
        "env": {},
        "icon": "📁",
    },
    {
        "slug": "kubernetes",
        "name": "Kubernetes",
        "description": "Manage Kubernetes clusters via kubectl MCP",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-kubernetes"],
        "env": {"KUBECONFIG": "~/.kube/config"},
        "icon": "☸️",
    },
    {
        "slug": "docker",
        "name": "Docker",
        "description": "Manage Docker containers and images",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-docker"],
        "env": {},
        "icon": "🐳",
    },
    {
        "slug": "postgres",
        "name": "PostgreSQL",
        "description": "Query and manage PostgreSQL databases",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env": {"POSTGRES_CONNECTION_STRING": "postgresql://user:pass@localhost/db"},
        "icon": "🐘",
    },
    {
        "slug": "slack",
        "name": "Slack",
        "description": "Send notifications and interact with Slack",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
        "icon": "💬",
    },
    {
        "slug": "custom_python",
        "name": "Custom Python MCP",
        "description": "Your own Python MCP server",
        "transport": "stdio",
        "command": "python",
        "args": ["path/to/your_mcp_server.py"],
        "env": {},
        "icon": "🐍",
    },
    {
        "slug": "keycloak_admin",
        "name": "Keycloak Admin",
        "description": "Manage Keycloak users, roles, clients, and groups via the project's Docker-friendly HTTP MCP",
        "transport": "sse",
        "command": "",
        "args": [],
        "env": {},
        "url": KEYCLOAK_TEMPLATE_URL,
        "icon": "🔐",
    },
]


@require_feature(STUDIO_FEATURE_MCP)
def api_mcp_list(request):
    if request.method == "GET":
        qs = _mcp_read_queryset_for_user(request.user)
        return _ok([_mcp_to_dict(mcp, request.user) for mcp in qs])

    if request.method == "POST":
        data = _json_body(request)
        name = data.get("name", "").strip()
        if not name:
            return _err("name is required")
        transport = data.get("transport", MCPServerPool.TRANSPORT_STDIO)
        url = (data.get("url") or "").strip()
        if transport == MCPServerPool.TRANSPORT_SSE and url:
            url = _normalize_sse_url(url)
        mcp = MCPServerPool.objects.create(
            name=name,
            description=data.get("description", ""),
            transport=transport,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=url,
            owner=request.user,
        )
        if _is_admin(request.user):
            if "is_shared" in data:
                mcp.is_shared = bool(data.get("is_shared"))
                mcp.save(update_fields=["is_shared"])
            if "shared_user_ids" in data:
                _apply_shared_users(mcp, _normalise_related_ids(data.get("shared_user_ids")))
        return _ok(_mcp_to_dict(mcp, request.user), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_MCP)
def api_mcp_detail(request, mcp_id: int):
    mcp = _mcp_read_queryset_for_user(request.user).filter(pk=mcp_id).first()
    if mcp is None:
        return _err("MCP server not found", 404)
    can_edit = _is_admin(request.user) or mcp.owner_id == request.user.id

    if request.method == "GET":
        return _ok(_mcp_to_dict(mcp, request.user))

    if request.method == "PUT":
        if not can_edit:
            return _err("Only the owner or admin can edit this MCP server", 403)
        data = _json_body(request)
        for field in ("name", "description", "transport", "command", "args", "env", "url"):
            if field in data:
                val = data[field]
                if field == "url" and (mcp.transport or data.get("transport")) == MCPServerPool.TRANSPORT_SSE and val:
                    val = _normalize_sse_url((val or "").strip())
                setattr(mcp, field, val)
        mcp.save()
        if _is_admin(request.user):
            if "is_shared" in data:
                mcp.is_shared = bool(data.get("is_shared"))
                mcp.save(update_fields=["is_shared"])
            if "shared_user_ids" in data:
                _apply_shared_users(mcp, _normalise_related_ids(data.get("shared_user_ids")))
        return _ok(_mcp_to_dict(mcp, request.user))

    if request.method == "DELETE":
        if not can_edit:
            return _err("Only the owner or admin can delete this MCP server", 403)
        mcp.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_MCP)
@require_http_methods(["POST"])
def api_mcp_test(request, mcp_id: int):
    mcp = _mcp_write_queryset_for_user(request.user).filter(pk=mcp_id).first()
    if mcp is None:
        return _err("MCP server not found", 404)

    ok, error = _test_mcp_connection(mcp)
    mcp.last_test_ok = ok
    mcp.last_test_at = timezone.now()
    mcp.last_test_error = error or ""
    mcp.save(update_fields=["last_test_ok", "last_test_at", "last_test_error"])
    return _ok({"ok": ok, "error": error})


def _normalize_sse_url(url: str) -> str:
    """Ensure SSE URL has http:// or https:// so httpx/requests accept it."""
    u = (url or "").strip()
    if not u:
        return u
    if u.startswith(("http://", "https://")):
        return u
    return "http://" + u


def _test_mcp_connection(mcp: MCPServerPool) -> tuple[bool, str | None]:
    """Basic connectivity test for MCP server."""
    import subprocess

    if mcp.transport == MCPServerPool.TRANSPORT_SSE:
        url = _normalize_sse_url(mcp.url or "")
        if not url:
            return False, "SSE URL is required"
        try:
            import httpx

            httpx.get(url, timeout=10)
            return True, None
        except Exception as exc:
            return False, str(exc)

    # stdio: try to start process and check it exits cleanly (or stays alive)
    if not mcp.command:
        return False, "No command configured"
    try:
        env = {**__import__("os").environ, **mcp.env, **get_mcp_secret_env(mcp.id)}
        proc = subprocess.Popen(
            [mcp.command] + (mcp.args or []),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            out, err = proc.communicate(timeout=5)
            return True, None
        except subprocess.TimeoutExpired:
            proc.kill()
            # Process stayed alive — likely a valid long-running MCP server
            return True, None
    except FileNotFoundError:
        return False, f"Command not found: {mcp.command}"
    except Exception as exc:
        return False, str(exc)


@require_feature(STUDIO_FEATURE_MCP)
def api_mcp_templates(request):
    return _ok(MCP_TEMPLATES)


@require_feature(STUDIO_FEATURE_MCP)
@require_http_methods(["GET"])
def api_mcp_tools(request, mcp_id: int):
    mcp = _mcp_read_queryset_for_user(request.user).filter(pk=mcp_id).first()
    if mcp is None:
        return _err("MCP server not found", 404)

    try:
        return _ok(asyncio.run(inspect_mcp_server(mcp)))
    except MCPClientError as exc:
        return _err(str(exc), 400)
    except Exception as exc:
        return _err(f"Failed to inspect MCP server: {exc}", 500)


@require_any_feature(STUDIO_FEATURE_SKILLS, STUDIO_FEATURE_MCP, STUDIO_FEATURE_AGENTS)
@require_http_methods(["GET"])
def api_share_users(request):
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    users = User.objects.filter(is_active=True).order_by("username")
    return _ok(
        [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email or "",
            }
            for user in users
        ]
    )


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_triggers(request):
    if request.method == "GET":
        pipeline_id = request.GET.get("pipeline_id")
        qs = PipelineTrigger.objects.filter(pipeline__in=_pipeline_queryset_for_user(request.user))
        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)
        return _ok([t.to_dict() for t in qs])

    if request.method == "POST":
        data = _json_body(request)
        pipeline_id = data.get("pipeline_id")
        if not pipeline_id:
            return _err("pipeline_id is required")
        pipeline = _get_pipeline(request, int(pipeline_id))
        if pipeline is None:
            return _err("Pipeline not found", 404)
        node_id = str(data.get("node_id", "") or "").strip()
        trigger_defaults = {
            "name": data.get("name", ""),
            "trigger_type": data.get("trigger_type", PipelineTrigger.TYPE_MANUAL),
            "is_active": data.get("is_active", True),
            "cron_expression": data.get("cron_expression", ""),
            "webhook_payload_map": data.get("webhook_payload_map", {}),
        }
        if node_id:
            trigger, _created = PipelineTrigger.objects.update_or_create(
                pipeline=pipeline,
                node_id=node_id,
                defaults=trigger_defaults,
            )
        else:
            trigger = PipelineTrigger.objects.create(
                pipeline=pipeline,
                node_id=node_id,
                **trigger_defaults,
            )
        return _ok(trigger.to_dict(), status=201)

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_trigger_detail(request, trigger_id: int):
    try:
        trigger = PipelineTrigger.objects.get(pk=trigger_id, pipeline__in=_pipeline_queryset_for_user(request.user))
    except PipelineTrigger.DoesNotExist:
        return _err("Trigger not found", 404)

    if request.method == "PUT":
        data = _json_body(request)
        next_node_id = str(data.get("node_id", trigger.node_id) or "").strip()
        if (
            next_node_id
            and next_node_id != trigger.node_id
            and PipelineTrigger.objects.filter(pipeline=trigger.pipeline, node_id=next_node_id).exclude(pk=trigger.pk).exists()
        ):
            return _err(f"Trigger for node '{next_node_id}' already exists")
        for field in ("node_id", "name", "trigger_type", "is_active", "cron_expression", "webhook_payload_map"):
            if field in data:
                setattr(trigger, field, data[field])
        trigger.save()
        return _ok(trigger.to_dict())

    if request.method == "DELETE":
        trigger.delete()
        return JsonResponse({"ok": True})

    return _err("Method not allowed", 405)


@csrf_exempt
@require_http_methods(["POST"])
def api_trigger_receive(request, token: str):
    """Public webhook endpoint — authenticated by token in URL."""
    try:
        trigger = PipelineTrigger.objects.select_related("pipeline").get(
            webhook_token=token,
            trigger_type=PipelineTrigger.TYPE_WEBHOOK,
            is_active=True,
        )
    except PipelineTrigger.DoesNotExist:
        return _err("Invalid token", 404)

    body = request.body.strip()
    if not body:
        payload = {}
    else:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _err("Webhook payload must be valid JSON")

    payload, error = ensure_json_object(payload, label="Webhook payload")
    if error:
        return _err(error)

    validation_errors = validate_pipeline_definition(nodes=trigger.pipeline.nodes, edges=trigger.pipeline.edges, owner=trigger.pipeline.owner)
    if validation_errors:
        return _validation_err(validation_errors, prefix="Pipeline is not runnable")

    context = _map_payload(payload, trigger.webhook_payload_map)

    limit_error = get_pipeline_run_limit_error(trigger.pipeline.owner)
    if limit_error:
        return JsonResponse(limit_error, status=429)

    run = PipelineRun.objects.create(
        pipeline=trigger.pipeline,
        trigger=trigger,
        status=PipelineRun.STATUS_PENDING,
        trigger_data=payload,
        context=context,
    )
    trigger.last_triggered_at = timezone.now()
    trigger.save(update_fields=["last_triggered_at"])

    _launch_pipeline_run_async(run)
    return _ok({"ok": True, "run_id": run.pk})


def _map_payload(payload: dict, mapping: dict) -> dict:
    """Map incoming webhook payload to pipeline context variables."""
    if not isinstance(payload, dict):
        return {}
    if not isinstance(mapping, dict):
        return dict(payload)
    if not mapping:
        return dict(payload)
    ctx = {}
    for ctx_key, payload_path in mapping.items():
        parts = payload_path.split(".")
        val = payload
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break
        ctx[ctx_key] = val
    return ctx


# ---------------------------------------------------------------------------
# Pipeline Templates
# ---------------------------------------------------------------------------


@require_feature(STUDIO_FEATURE_PIPELINES)
def api_templates(request):
    templates = PipelineTemplate.objects.all().order_by("category", "name")
    return _ok([t.to_dict() for t in templates])


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_template_use(request, slug: str):
    try:
        template = PipelineTemplate.objects.get(slug=slug)
    except PipelineTemplate.DoesNotExist:
        return _err("Template not found", 404)
    pipeline = template.instantiate_for_user(request.user)
    pipeline.sync_triggers_from_nodes()
    return _ok(pipeline.to_detail_dict(), status=201)


# ---------------------------------------------------------------------------
# Servers (for node config dropdowns)
# ---------------------------------------------------------------------------


@require_any_feature(STUDIO_FEATURE_PIPELINES, STUDIO_FEATURE_AGENTS)
def api_studio_servers(request):
    from servers.models import Server

    servers = Server.objects.filter(user=request.user).order_by("name")
    return _ok([{"id": s.pk, "name": s.name, "host": s.host} for s in servers])


# ---------------------------------------------------------------------------
# Notification settings
# ---------------------------------------------------------------------------


@require_feature(STUDIO_FEATURE_NOTIFICATIONS)
def api_notification_settings(request):
    """
    GET  /api/studio/notifications/  — return current notification settings
    POST /api/studio/notifications/  — save notification settings
    """
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error

    if request.method == "GET":
        cfg = _load_notif_config()
        # Mask password in GET response
        masked = dict(cfg)
        if masked.get("smtp_password"):
            masked["smtp_password"] = "••••••••"
        if masked.get("telegram_bot_token") and len(masked["telegram_bot_token"]) > 10:
            tok = masked["telegram_bot_token"]
            masked["telegram_bot_token"] = tok[:8] + "•" * (len(tok) - 8)
        return _ok(masked)

    if request.method == "POST":
        data = _json_body(request)
        allowed = set(_NOTIF_DEFAULTS.keys())
        to_save = {k: v for k, v in data.items() if k in allowed}
        # Don't overwrite password with mask placeholder
        if to_save.get("smtp_password", "").startswith("•"):
            existing = _load_notif_config()
            to_save["smtp_password"] = existing.get("smtp_password", "")
        if to_save.get("telegram_bot_token", "").endswith("•" * 4):
            existing = _load_notif_config()
            to_save["telegram_bot_token"] = existing.get("telegram_bot_token", "")
        _save_notif_config(to_save)
        return _ok({"ok": True, "saved": list(to_save.keys())})

    return _err("Method not allowed", 405)


@require_feature(STUDIO_FEATURE_NOTIFICATIONS)
@require_http_methods(["POST"])
def api_notification_test_telegram(request):
    """POST /api/studio/notifications/test-telegram/ — send a test Telegram message."""
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    import asyncio

    cfg = _load_notif_config()
    bot_token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()

    if not bot_token or not chat_id:
        return _err("Telegram bot_token and chat_id must be configured first.")

    async def _send():
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "✅ *WEU Platform* — Telegram notifications are working correctly!",
                    "parse_mode": "Markdown",
                },
            )
            return resp.status_code, resp.text[:300]

    try:
        code, body = asyncio.run(_send())
        if code == 200:
            return _ok({"ok": True, "message": f"Test message sent to chat {chat_id}"})
        return _err(f"Telegram API returned {code}: {body}")
    except Exception as exc:
        return _err(f"Send failed: {exc}")


@require_feature(STUDIO_FEATURE_NOTIFICATIONS)
@require_http_methods(["POST"])
def api_notification_test_email(request):
    """POST /api/studio/notifications/test-email/ — send a test email."""
    admin_error = _require_admin(request)
    if admin_error:
        return admin_error
    import smtplib
    from email.mime.text import MIMEText

    cfg = _load_notif_config()
    to_email = cfg.get("notify_email", "").strip()
    smtp_host = cfg.get("smtp_host", "").strip() or getattr(django_settings, "EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(cfg.get("smtp_port") or getattr(django_settings, "EMAIL_PORT", 587))
    smtp_user = cfg.get("smtp_user", "").strip() or getattr(django_settings, "EMAIL_HOST_USER", "")
    smtp_password = cfg.get("smtp_password", "").strip() or getattr(django_settings, "EMAIL_HOST_PASSWORD", "")
    from_email = cfg.get("from_email", "").strip() or smtp_user or getattr(django_settings, "DEFAULT_FROM_EMAIL", "") or "pipeline@noreply.local"
    from_email = _resolve_from_email_smtp(from_email, smtp_user, smtp_host)

    # Recipient must be a full email; if user entered only login (e.g. germane.keller), add domain
    to_email = _normalize_email_recipient(to_email, smtp_host)

    if not to_email:
        return _err("notify_email is not configured.")
    if not smtp_user:
        return _err("smtp_user (email login) is not configured.")

    try:
        msg = MIMEText("✅ WEU Platform — Email notifications are working correctly!", "plain", "utf-8")
        msg["Subject"] = "WEU Platform — Test Email"
        msg["From"] = from_email
        msg["To"] = to_email

        # Port 465 = SSL from the start (Yandex); 587 = STARTTLS
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                if smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, [to_email], msg.as_string())

        return _ok({"ok": True, "message": f"Test email sent to {to_email}"})
    except Exception as exc:
        return _err(f"SMTP error: {exc}")


# ---------------------------------------------------------------------------
# Background run launcher
# ---------------------------------------------------------------------------


def _launch_pipeline_run_async(run: PipelineRun):
    """Launch pipeline execution in a background thread (Django dev server)."""

    run_pk = run.pk

    def _run_in_thread():
        try:
            async def _main():
                from asgiref.sync import sync_to_async

                from studio.pipeline_executor import PipelineExecutor

                run_obj = await sync_to_async(
                    lambda: PipelineRun.objects.select_related("pipeline", "pipeline__owner", "triggered_by").get(pk=run_pk)
                )()
                executor = PipelineExecutor(run_obj)
                await executor.execute(context=run_obj.context)

            asyncio.run(_main())
        except Exception as exc:
            PipelineRun.objects.filter(pk=run_pk).update(
                status=PipelineRun.STATUS_FAILED,
                error=str(exc),
                finished_at=timezone.now(),
            )

    thread = threading.Thread(target=_run_in_thread, daemon=True)
    thread.start()
