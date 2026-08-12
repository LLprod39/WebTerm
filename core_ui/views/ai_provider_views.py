"""REST API for subscription CLI connections, pools, grants, and defaults."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from app.ai_runtime import ExecutionMode, ProviderBinding, ProviderTarget, canonicalize_target_id
from core_ui.activity import log_user_activity
from core_ui.context_processors import user_can_feature
from core_ui.models.ai_providers import (
    AIConnectionAuthFlow,
    AIProviderConnection,
    AIProviderConnectionGrant,
    AIProviderPool,
    AIProviderPoolMember,
    AIProviderPreference,
)
from core_ui.models.projects import Project
from core_ui.schemas.openapi_metadata import openapi_responses
from core_ui.services.ai_provider_access import can_use_binding, can_use_connection
from core_ui.services.ai_provider_auth import (
    cancel_pending_auth_flows,
    fence_connection_invocations,
    queue_connection_verification,
    revoke_connection_credentials,
    start_connection_auth,
)

logger = logging.getLogger(__name__)


def _body(request) -> dict[str, Any]:
    try:
        value = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Invalid JSON body") from None
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def _error(message: str, status: int = 400, *, code: str = "invalid_request") -> JsonResponse:
    return JsonResponse({"success": False, "error": message, "code": code}, status=status)


def _validation_error(fields: dict[str, list[str] | str]) -> JsonResponse:
    normalized = {str(field): value if isinstance(value, list) else [str(value)] for field, value in fields.items()}
    return JsonResponse(
        {
            "success": False,
            "error": "Validation failed",
            "code": "validation_error",
            "fields": normalized,
        },
        status=400,
    )


class _FieldsValidationError(ValueError):
    def __init__(self, fields: dict[str, list[str] | str]):
        super().__init__("Validation failed")
        self.fields = fields


def _strict_int(value: Any, *, field: str, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise _FieldsValidationError({field: "Must be an integer, not a boolean"})
    if not isinstance(value, int):
        raise _FieldsValidationError({field: "Must be an integer"})
    parsed = value
    if parsed < minimum or (maximum is not None and parsed > maximum):
        limit = f" between {minimum} and {maximum}" if maximum is not None else f" at least {minimum}"
        raise _FieldsValidationError({field: f"Must be{limit}"})
    return parsed


def _provider_surface_guard(request, *, admin: bool = False) -> JsonResponse | None:
    if os.getenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return _error("Subscription CLI providers are disabled", 404, code="feature_disabled")
    feature = "ai_connections_admin" if admin else "ai_connections_personal"
    if not user_can_feature(request.user, feature, request=request):
        return _error("AI connection access is not granted", 403, code="permission_denied")
    return None


def _can_admin_ai_connections(user, *, request=None) -> bool:
    return user_can_feature(user, "ai_connections_admin", request=request)


def _strict_bool(value: Any, *, field: str, default: bool | None = None) -> bool:
    if value is None and default is not None:
        return default
    if not isinstance(value, bool):
        raise _FieldsValidationError({field: "Must be a boolean"})
    return value


def _audit_provider_mutation(
    request,
    *,
    action: str,
    entity_type: str,
    entity_id: int | str,
    target_id: str = "",
    scope: str = "",
    outcome: str = "success",
) -> None:
    log_user_activity(
        request=request,
        category="security",
        action=action,
        status="success" if outcome == "success" else "error",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={
            "target_id": target_id,
            "scope": scope,
            "outcome": outcome,
        },
    )


def _active_project_id(user) -> int | None:
    membership = user.project_memberships.filter(is_active=True).values_list("project_id", flat=True).first()
    if membership:
        return membership
    return Project.objects.filter(owner=user, is_default=True).values_list("id", flat=True).first()


def _connection_access(connection: AIProviderConnection, user) -> dict[str, bool]:
    project_id = _active_project_id(user)
    return {
        "interactive": can_use_connection(
            connection,
            user_id=user.pk,
            project_id=project_id,
            mode=ExecutionMode.INTERACTIVE,
        ).allowed,
        "unattended": can_use_connection(
            connection,
            user_id=user.pk,
            project_id=project_id,
            mode=ExecutionMode.UNATTENDED,
        ).allowed,
    }


def _serialize_connection(connection: AIProviderConnection, user, *, include_grants: bool = False) -> dict[str, Any]:
    payload = {
        "id": connection.pk,
        "public_id": str(connection.public_id),
        "target_id": connection.target_id,
        "scope": connection.scope,
        "owner_id": connection.owner_id,
        "name": connection.name,
        "status": connection.status,
        "enabled": connection.enabled,
        "runtime_version": connection.runtime_version,
        "auth_revision": connection.auth_revision,
        "concurrency_limit": connection.concurrency_limit,
        "health": connection.health or {},
        "limits": connection.limits or {},
        "last_error_code": connection.last_error_code,
        "last_verified_at": connection.last_verified_at.isoformat() if connection.last_verified_at else None,
        "access": _connection_access(connection, user),
        "manageable": bool(connection.owner_id == user.pk or _can_admin_ai_connections(user)),
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
    }
    if include_grants and _can_admin_ai_connections(user):
        payload["grants"] = [
            _serialize_grant(item) for item in connection.grants.select_related("user", "group", "project")
        ]
    return payload


def _serialize_grant(grant: AIProviderConnectionGrant) -> dict[str, Any]:
    return {
        "id": grant.pk,
        "connection_id": grant.connection_id,
        "user": {"id": grant.user_id, "username": grant.user.username} if grant.user_id else None,
        "group": {"id": grant.group_id, "name": grant.group.name} if grant.group_id else None,
        "project": {"id": grant.project_id, "name": grant.project.name} if grant.project_id else None,
        "project_role": grant.project_role,
        "allow_interactive": grant.allow_interactive,
        "allow_unattended": grant.allow_unattended,
    }


def _connection_queryset_for(user):
    candidates = AIProviderConnection.objects.select_related("owner").prefetch_related(
        "grants__user", "grants__group", "grants__project"
    )
    if _can_admin_ai_connections(user):
        return candidates
    project_id = _active_project_id(user)
    allowed_ids = []
    for connection in candidates.filter(scope=AIProviderConnection.SCOPE_WORKSPACE):
        if (
            can_use_connection(
                connection,
                user_id=user.pk,
                project_id=project_id,
                mode=ExecutionMode.INTERACTIVE,
            ).allowed
            or can_use_connection(
                connection,
                user_id=user.pk,
                project_id=project_id,
                mode=ExecutionMode.UNATTENDED,
            ).allowed
        ):
            allowed_ids.append(connection.pk)
    return candidates.filter(models.Q(owner=user) | models.Q(pk__in=allowed_ids))


@login_required
@require_http_methods(["GET"])
def api_ai_provider_catalog(request):
    if denied := _provider_surface_guard(request):
        return denied
    return JsonResponse(
        {
            "success": True,
            "targets": [
                {
                    "id": ProviderTarget.CODEX_SUBSCRIPTION.value,
                    "label": "Codex CLI (ChatGPT subscription)",
                    "auth": "device_code",
                    "kind": "subscription_cli",
                },
                {
                    "id": ProviderTarget.GROK_SUBSCRIPTION.value,
                    "label": "Grok CLI (xAI subscription)",
                    "auth": "device_code",
                    "kind": "subscription_cli",
                },
                *[
                    {"id": target.value, "label": target.value, "kind": "platform"}
                    for target in ProviderTarget
                    if target not in {ProviderTarget.CODEX_SUBSCRIPTION, ProviderTarget.GROK_SUBSCRIPTION}
                ],
            ],
            "purposes": [item[0] for item in AIProviderPreference.PURPOSE_CHOICES],
            "scopes": [item[0] for item in AIProviderConnection.SCOPE_CHOICES],
        }
    )


@login_required
@require_http_methods(["GET", "POST"])
def api_ai_provider_connections(request):
    if denied := _provider_surface_guard(request):
        return denied
    if request.method == "GET":
        rows = _connection_queryset_for(request.user)
        return JsonResponse(
            {
                "success": True,
                "connections": [_serialize_connection(item, request.user, include_grants=True) for item in rows],
            }
        )
    try:
        data = _body(request)
        target_id = canonicalize_target_id(str(data.get("target_id") or ""))
    except ValueError as exc:
        return _error(str(exc))
    if target_id not in {
        ProviderTarget.CODEX_SUBSCRIPTION.value,
        ProviderTarget.GROK_SUBSCRIPTION.value,
    }:
        return _error("Only subscription CLI targets can create connections")
    scope = str(data.get("scope") or AIProviderConnection.SCOPE_PERSONAL)
    if scope not in {AIProviderConnection.SCOPE_PERSONAL, AIProviderConnection.SCOPE_WORKSPACE}:
        return _error("scope must be personal or workspace")
    if scope == AIProviderConnection.SCOPE_WORKSPACE and (denied := _provider_surface_guard(request, admin=True)):
        return denied
    name = str(data.get("name") or "").strip()[:120]
    if not name:
        return _error("name is required")
    try:
        concurrency = _strict_int(
            data.get("concurrency_limit", 1),
            field="concurrency_limit",
            minimum=1,
            maximum=8,
        )
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    connection = AIProviderConnection.objects.create(
        target_id=target_id,
        scope=scope,
        owner=request.user if scope == AIProviderConnection.SCOPE_PERSONAL else None,
        created_by=request.user,
        name=name,
        concurrency_limit=concurrency,
    )
    return JsonResponse(
        {"success": True, "connection": _serialize_connection(connection, request.user, include_grants=True)},
        status=201,
    )


def _manageable_connection(request, connection_id: int) -> AIProviderConnection | JsonResponse:
    connection = get_object_or_404(AIProviderConnection, pk=connection_id)
    if connection.owner_id == request.user.pk:
        return connection
    if not _can_admin_ai_connections(request.user, request=request):
        return _error("Connection is not manageable", 403, code="permission_denied")
    return connection


@login_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_ai_provider_connection_detail(request, connection_id: int):
    if denied := _provider_surface_guard(request):
        return denied
    connection = _manageable_connection(request, connection_id)
    if isinstance(connection, JsonResponse):
        return connection
    if request.method == "GET":
        return JsonResponse(
            {"success": True, "connection": _serialize_connection(connection, request.user, include_grants=True)}
        )
    if request.method == "DELETE":
        # Fail closed before contacting the manager: no new route may select
        # this connection, and active leases are fenced from durable writes.
        connection.enabled = False
        connection.status = AIProviderConnection.STATUS_DISABLED
        connection.save(update_fields=["enabled", "status", "updated_at"])
        cancel_pending_auth_flows(connection)
        fence_connection_invocations(connection)
        try:
            if not revoke_connection_credentials(connection):
                raise RuntimeError("credential cleanup was not acknowledged")
        except Exception:
            connection.health = {**(connection.health or {}), "cleanup_pending": True}
            connection.last_error_code = "provider_credential_cleanup_pending"
            connection.save(update_fields=["health", "last_error_code", "updated_at"])
            _audit_provider_mutation(
                request,
                action="ai_provider.connection.revoke",
                entity_type="ai_provider_connection",
                entity_id=connection.pk,
                target_id=connection.target_id,
                scope=connection.scope,
                outcome="cleanup_pending",
            )
            return JsonResponse(
                {
                    "success": True,
                    "revoked": False,
                    "cleanup_pending": True,
                    "code": "provider_credential_cleanup_pending",
                },
                status=202,
            )
        connection.enabled = False
        connection.status = AIProviderConnection.STATUS_REVOKED
        connection.credential_ref = ""
        connection.health = {key: value for key, value in (connection.health or {}).items() if key != "cleanup_pending"}
        connection.last_error_code = ""
        connection.save(
            update_fields=["enabled", "status", "credential_ref", "health", "last_error_code", "updated_at"]
        )
        _audit_provider_mutation(
            request,
            action="ai_provider.connection.revoke",
            entity_type="ai_provider_connection",
            entity_id=connection.pk,
            target_id=connection.target_id,
            scope=connection.scope,
        )
        return JsonResponse({"success": True, "revoked": True})
    try:
        data = _body(request)
    except ValueError as exc:
        return _error(str(exc))
    if "name" in data:
        connection.name = str(data.get("name") or "").strip()[:120]
        if not connection.name:
            return _error("name is required")
    if "enabled" in data:
        try:
            connection.enabled = _strict_bool(data.get("enabled"), field="enabled")
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
        if not connection.enabled and connection.status == AIProviderConnection.STATUS_CONNECTED:
            connection.status = AIProviderConnection.STATUS_DISABLED
    if "concurrency_limit" in data:
        try:
            connection.concurrency_limit = _strict_int(
                data.get("concurrency_limit"),
                field="concurrency_limit",
                minimum=1,
                maximum=8,
            )
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
    connection.save()
    return JsonResponse(
        {"success": True, "connection": _serialize_connection(connection, request.user, include_grants=True)}
    )


@login_required
@require_http_methods(["POST"])
@openapi_responses(
    {
        200: None,
        202: {
            "description": "Provider authentication flow accepted",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiSuccessResponse"}}},
        },
        404: {
            "description": "AI CLI provider feature is disabled",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}}},
        },
    }
)
def api_ai_provider_connection_auth(request, connection_id: int):
    if denied := _provider_surface_guard(request):
        return denied
    connection = _manageable_connection(request, connection_id)
    if isinstance(connection, JsonResponse):
        return connection
    try:
        flow = start_connection_auth(connection)
    except Exception as exc:
        logger.warning(
            "AI provider auth queue failed target=%s connection_id=%s error_type=%s",
            connection.target_id,
            connection.pk,
            type(exc).__name__,
        )
        return _error(
            "Provider authentication is temporarily unavailable",
            503,
            code="provider_transport_unavailable",
        )
    return JsonResponse({"success": True, "auth_flow": _serialize_auth_flow(flow)}, status=202)


def _serialize_auth_flow(flow: AIConnectionAuthFlow) -> dict[str, Any]:
    return {
        "id": str(flow.public_id),
        "connection_id": flow.connection_id,
        "status": flow.status,
        "verification_uri": flow.verification_uri,
        "user_code": flow.user_code,
        "error_code": flow.error_code,
        "expires_at": flow.expires_at.isoformat() if flow.expires_at else None,
        "created_at": flow.created_at.isoformat(),
        "completed_at": flow.completed_at.isoformat() if flow.completed_at else None,
    }


@login_required
@require_http_methods(["GET"])
def api_ai_provider_auth_flow(request, flow_id):
    if denied := _provider_surface_guard(request):
        return denied
    flow = get_object_or_404(AIConnectionAuthFlow.objects.select_related("connection"), public_id=flow_id)
    manageable = flow.connection.owner_id == request.user.pk or _can_admin_ai_connections(request.user, request=request)
    if not manageable:
        return _error("Auth flow is not accessible", 403, code="permission_denied")
    return JsonResponse({"success": True, "auth_flow": _serialize_auth_flow(flow)})


@login_required
@require_http_methods(["POST"])
@openapi_responses(
    {
        200: None,
        202: {
            "description": "Provider verification flow accepted",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiSuccessResponse"}}},
        },
        404: {
            "description": "AI CLI provider feature is disabled",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}}},
        },
    }
)
def api_ai_provider_connection_verify(request, connection_id: int):
    if denied := _provider_surface_guard(request):
        return denied
    connection = _manageable_connection(request, connection_id)
    if isinstance(connection, JsonResponse):
        return connection
    if not connection.credential_ref:
        return _error("Connection has not been authenticated", 409, code="provider_auth_required")
    flow = queue_connection_verification(connection)
    return JsonResponse({"success": True, "auth_flow": _serialize_auth_flow(flow)}, status=202)


def _serialize_pool(pool: AIProviderPool, user) -> dict[str, Any]:
    members = []
    for member in pool.members.select_related("connection"):
        access = _connection_access(member.connection, user)
        if _can_admin_ai_connections(user) or access["interactive"] or access["unattended"]:
            members.append(
                {
                    "id": member.pk,
                    "connection_id": member.connection_id,
                    "connection_name": member.connection.name,
                    "status": member.connection.status,
                    "enabled": member.enabled,
                    "weight": member.weight,
                    "access": access,
                }
            )
    return {
        "id": pool.pk,
        "public_id": str(pool.public_id),
        "name": pool.name,
        "target_id": pool.target_id,
        "enabled": pool.enabled,
        "members": members,
        "manageable": _can_admin_ai_connections(user),
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_ai_provider_pools(request):
    if denied := _provider_surface_guard(request, admin=True):
        return denied
    if request.method == "GET":
        pools = [
            _serialize_pool(pool, request.user)
            for pool in AIProviderPool.objects.prefetch_related("members__connection")
        ]
        if not _can_admin_ai_connections(request.user, request=request):
            pools = [pool for pool in pools if pool["members"]]
        return JsonResponse({"success": True, "pools": pools})
    try:
        data = _body(request)
        target_id = canonicalize_target_id(str(data.get("target_id") or ""))
    except ValueError as exc:
        return _error(str(exc))
    if target_id not in {ProviderTarget.CODEX_SUBSCRIPTION.value, ProviderTarget.GROK_SUBSCRIPTION.value}:
        return _error("Pools accept only subscription CLI targets")
    name = str(data.get("name") or "").strip()[:120]
    if not name:
        return _error("name is required")
    try:
        members = _normalize_pool_members(data, target_id=target_id)
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    try:
        with transaction.atomic():
            pool = AIProviderPool.objects.create(name=name, target_id=target_id, created_by=request.user)
            _replace_pool_members(pool, members)
    except IntegrityError:
        return _error("A provider pool with this name already exists")
    return JsonResponse({"success": True, "pool": _serialize_pool(pool, request.user)}, status=201)


def _normalize_pool_members(data: dict[str, Any], *, target_id: str) -> list[dict[str, Any]]:
    raw = data.get("members")
    if raw is None:
        raw_ids = data.get("connection_ids", [])
        if not isinstance(raw_ids, list):
            raise _FieldsValidationError({"connection_ids": "Must be an array"})
        raw = [{"connection_id": value, "weight": 1, "enabled": True} for value in raw_ids]
    if not isinstance(raw, list):
        raise _FieldsValidationError({"members": "Must be an array"})
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    fields: dict[str, list[str] | str] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            fields[f"members.{index}"] = "Must be an object"
            continue
        try:
            connection_id = _strict_int(
                item.get("connection_id"),
                field=f"members.{index}.connection_id",
                minimum=1,
            )
        except _FieldsValidationError as exc:
            fields.update(exc.fields)
            continue
        try:
            weight = _strict_int(
                item.get("weight", 1),
                field=f"members.{index}.weight",
                minimum=1,
                maximum=100,
            )
        except _FieldsValidationError as exc:
            fields.update(exc.fields)
            continue
        if connection_id in seen:
            fields[f"members.{index}.connection_id"] = "Duplicate connection ID"
            continue
        try:
            enabled = _strict_bool(
                item.get("enabled"),
                field=f"members.{index}.enabled",
                default=True,
            )
        except _FieldsValidationError as exc:
            fields.update(exc.fields)
            continue
        seen.add(connection_id)
        normalized.append(
            {
                "connection_id": connection_id,
                "weight": weight,
                "enabled": enabled,
                "_input_index": index,
            }
        )
    if fields:
        raise _FieldsValidationError(fields)
    valid_ids = set(
        AIProviderConnection.objects.filter(
            pk__in=seen,
            scope=AIProviderConnection.SCOPE_WORKSPACE,
            target_id=target_id,
        ).values_list("pk", flat=True)
    )
    if valid_ids != seen:
        missing = seen - valid_ids
        for item in normalized:
            if item["connection_id"] in missing:
                fields[f"members.{item['_input_index']}.connection_id"] = (
                    "Must reference an existing workspace connection for this target"
                )
        raise _FieldsValidationError(fields)
    return [
        {"connection_id": item["connection_id"], "weight": item["weight"], "enabled": item["enabled"]}
        for item in normalized
    ]


def _replace_pool_members(pool: AIProviderPool, members: list[dict[str, Any]]) -> None:
    normalized = {item["connection_id"]: item for item in members}
    connections = AIProviderConnection.objects.filter(pk__in=normalized)
    with transaction.atomic():
        pool.members.exclude(connection_id__in=[item.pk for item in connections]).delete()
        for connection in connections:
            AIProviderPoolMember.objects.update_or_create(
                pool=pool,
                connection=connection,
                defaults={
                    "enabled": normalized[connection.pk]["enabled"],
                    "weight": normalized[connection.pk]["weight"],
                },
            )


@login_required
@require_http_methods(["PATCH", "DELETE"])
def api_ai_provider_pool_detail(request, pool_id: int):
    if denied := _provider_surface_guard(request, admin=True):
        return denied
    pool = get_object_or_404(AIProviderPool, pk=pool_id)
    if request.method == "DELETE":
        target_id = pool.target_id
        entity_id = pool.pk
        pool.delete()
        _audit_provider_mutation(
            request,
            action="ai_provider.pool.delete",
            entity_type="ai_provider_pool",
            entity_id=entity_id,
            target_id=target_id,
            scope="workspace",
        )
        return JsonResponse({"success": True})
    try:
        data = _body(request)
    except ValueError as exc:
        return _error(str(exc))
    if "name" in data:
        pool.name = str(data.get("name") or "").strip()[:120]
        if not pool.name:
            return _error("name is required")
        if AIProviderPool.objects.exclude(pk=pool.pk).filter(name=pool.name).exists():
            return _error("A provider pool with this name already exists")
    if "enabled" in data:
        try:
            pool.enabled = _strict_bool(data.get("enabled"), field="enabled")
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
    pool.save()
    if "connection_ids" in data or "members" in data:
        try:
            members = _normalize_pool_members(data, target_id=pool.target_id)
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
        _replace_pool_members(pool, members)
    return JsonResponse({"success": True, "pool": _serialize_pool(pool, request.user)})


@login_required
@require_http_methods(["POST"])
def api_ai_provider_grants(request):
    if denied := _provider_surface_guard(request, admin=True):
        return denied
    try:
        data = _body(request)
    except ValueError as exc:
        return _error(str(exc))
    try:
        connection_id = _strict_int(data.get("connection_id"), field="connection_id", minimum=1)
        principal_names = ("user_id", "group_id", "project_id")
        supplied_principals = [name for name in principal_names if data.get(name) is not None]
        if len(supplied_principals) != 1:
            raise _FieldsValidationError({"principal": "Exactly one of user_id, group_id, project_id is required"})
        principal_name = supplied_principals[0]
        principal_id = _strict_int(data.get(principal_name), field=principal_name, minimum=1)
        defaults = {
            "allow_interactive": _strict_bool(data.get("allow_interactive"), field="allow_interactive", default=True),
            "allow_unattended": _strict_bool(data.get("allow_unattended"), field="allow_unattended", default=False),
        }
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    connection = AIProviderConnection.objects.filter(
        pk=connection_id,
        scope=AIProviderConnection.SCOPE_WORKSPACE,
    ).first()
    if connection is None:
        return _validation_error({"connection_id": "Workspace connection does not exist"})
    if principal_name == "user_id":
        user = User.objects.filter(pk=principal_id).first()
        if user is None:
            return _validation_error({"user_id": "User does not exist"})
        grant, _ = AIProviderConnectionGrant.objects.update_or_create(
            connection=connection,
            user=user,
            defaults=defaults,
        )
    elif principal_name == "group_id":
        group = Group.objects.filter(pk=principal_id).first()
        if group is None:
            return _validation_error({"group_id": "Group does not exist"})
        grant, _ = AIProviderConnectionGrant.objects.update_or_create(
            connection=connection,
            group=group,
            defaults=defaults,
        )
    else:
        project = Project.objects.filter(pk=principal_id).first()
        if project is None:
            return _validation_error({"project_id": "Project does not exist"})
        role = str(data.get("project_role") or "")[:20]
        grant, _ = AIProviderConnectionGrant.objects.update_or_create(
            connection=connection,
            project=project,
            project_role=role,
            defaults=defaults,
        )
    return JsonResponse({"success": True, "grant": _serialize_grant(grant)}, status=201)


@login_required
@require_http_methods(["DELETE"])
def api_ai_provider_grant_detail(request, grant_id: int):
    if denied := _provider_surface_guard(request, admin=True):
        return denied
    grant = get_object_or_404(AIProviderConnectionGrant.objects.select_related("connection"), pk=grant_id)
    connection = grant.connection
    grant.delete()
    _audit_provider_mutation(
        request,
        action="ai_provider.grant.delete",
        entity_type="ai_provider_connection_grant",
        entity_id=grant_id,
        target_id=connection.target_id,
        scope=connection.scope,
    )
    return JsonResponse({"success": True})


def _serialize_preference(preference: AIProviderPreference) -> dict[str, Any]:
    return {
        "id": preference.pk,
        "user_id": preference.user_id,
        "project_id": preference.project_id,
        "purpose": preference.purpose,
        "binding": {
            "target_id": preference.target_id,
            "connection_id": preference.connection_id,
            "pool_id": preference.pool_id,
            "model_id": preference.model_id or None,
        },
    }


def _save_preference(
    request,
    *,
    data: dict[str, Any],
    filters: dict[str, Any],
    workspace_default: bool,
    project_id: int | None,
) -> JsonResponse:
    try:
        binding = ProviderBinding.from_dict(data.get("binding") or {})
    except ValueError as exc:
        return _error(str(exc))
    if binding.connection_id is not None:
        connection = AIProviderConnection.objects.filter(pk=binding.connection_id).first()
        if connection is None or connection.target_id != binding.target_id:
            return _error("Connection does not exist or targets another provider")
        if workspace_default and connection.scope != AIProviderConnection.SCOPE_WORKSPACE:
            return _error("Workspace defaults cannot use a personal connection")
    if binding.pool_id is not None:
        pool = AIProviderPool.objects.filter(pk=binding.pool_id, enabled=True).first()
        if pool is None or pool.target_id != binding.target_id:
            return _error("Pool does not exist or targets another provider")
    if not workspace_default:
        try:
            require_unattended = _strict_bool(data.get("require_unattended"), field="require_unattended", default=False)
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
        mode = ExecutionMode.UNATTENDED if require_unattended else ExecutionMode.INTERACTIVE
        decision = can_use_binding(binding, user_id=request.user.pk, project_id=project_id, mode=mode)
        if not decision.allowed:
            return _error(
                f"Selected binding is unavailable: {decision.reason}",
                403,
                code="provider_route_unavailable",
            )
    defaults = {
        "target_id": binding.target_id,
        "connection_id": binding.connection_id,
        "pool_id": binding.pool_id,
        "model_id": binding.model_id or "",
    }
    preference, _ = AIProviderPreference.objects.update_or_create(defaults=defaults, **filters)
    return JsonResponse({"success": True, "preference": _serialize_preference(preference)})


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_ai_provider_preferences(request):
    if denied := _provider_surface_guard(request):
        return denied
    project_id = _active_project_id(request.user)
    if request.method == "GET":
        scope_filter = models.Q(project__isnull=True)
        if project_id:
            scope_filter |= models.Q(project_id=project_id)
        rows = list(
            AIProviderPreference.objects.filter(scope_filter, user=request.user).select_related("connection", "pool")
        )
        workspace = []
        if project_id:
            workspace = list(AIProviderPreference.objects.filter(user__isnull=True, project_id=project_id))
        return JsonResponse(
            {
                "success": True,
                "preferences": [_serialize_preference(item) for item in rows],
                "workspace_defaults": [_serialize_preference(item) for item in workspace],
            }
        )
    try:
        data = _body(request)
        purpose = str(data.get("purpose") or "")
        if purpose not in {item[0] for item in AIProviderPreference.PURPOSE_CHOICES}:
            raise ValueError("Unknown preference purpose")
    except ValueError as exc:
        return _error(str(exc))
    try:
        workspace_default = _strict_bool(data.get("workspace_default"), field="workspace_default", default=False)
        project_scoped = _strict_bool(data.get("project_scoped"), field="project_scoped", default=True)
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    if workspace_default and (denied := _provider_surface_guard(request, admin=True)):
        return denied
    preference_project_id = project_id if project_scoped else None
    if workspace_default and preference_project_id is None:
        return _error("An active project is required for a workspace default")
    filters = {
        "user": None if workspace_default else request.user,
        "project_id": preference_project_id,
        "purpose": purpose,
    }
    if request.method == "DELETE":
        deleted_ids = list(AIProviderPreference.objects.filter(**filters).values_list("pk", flat=True))
        AIProviderPreference.objects.filter(pk__in=deleted_ids).delete()
        if workspace_default:
            for preference_id in deleted_ids:
                _audit_provider_mutation(
                    request,
                    action="ai_provider.workspace_default.delete",
                    entity_type="ai_provider_preference",
                    entity_id=preference_id,
                    scope="workspace",
                )
        return JsonResponse({"success": True})
    return _save_preference(
        request,
        data=data,
        filters=filters,
        workspace_default=workspace_default,
        project_id=preference_project_id,
    )
