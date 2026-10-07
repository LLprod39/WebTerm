"""REST API for subscription CLI connections, pools, grants, and defaults."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import IntegrityError, models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from app.ai_runtime import ExecutionMode, ProviderBinding, ProviderRuntimeError, ProviderTarget, canonicalize_target_id
from core_ui.activity import log_user_activity
from core_ui.ai_model_policy import user_can_manage_ai_routing
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
    submit_authorization_code,
    fence_connection_invocations,
    queue_connection_verification,
    revoke_connection_credentials,
    start_connection_auth,
)

logger = logging.getLogger(__name__)

# The runner image is pinned, so this catalog matches the Codex SDK shipped in
# that image. Unsupported model/effort pairs are rejected before a run starts.
CODEX_SUBSCRIPTION_MODELS = [
    {"id": "gpt-5.6-sol", "label": "GPT-5.6 Sol", "default_reasoning_effort": "low", "reasoning_efforts": ["low", "medium", "high", "xhigh", "max", "ultra"]},
    {"id": "gpt-5.6-terra", "label": "GPT-5.6 Terra", "default_reasoning_effort": "medium", "reasoning_efforts": ["low", "medium", "high", "xhigh", "max", "ultra"]},
    {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna", "default_reasoning_effort": "medium", "reasoning_efforts": ["low", "medium", "high", "xhigh", "max"]},
    {"id": "gpt-5.5", "label": "GPT-5.5", "default_reasoning_effort": "medium", "reasoning_efforts": ["low", "medium", "high", "xhigh"]},
    {"id": "gpt-5.4", "label": "GPT-5.4", "default_reasoning_effort": "medium", "reasoning_efforts": ["low", "medium", "high", "xhigh"], "deprecated": True},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "default_reasoning_effort": "medium", "reasoning_efforts": ["low", "medium", "high", "xhigh"], "deprecated": True},
    {"id": "gpt-5.3-codex-spark", "label": "GPT-5.3 Codex Spark", "default_reasoning_effort": "high", "reasoning_efforts": ["low", "medium", "high", "xhigh"]},
]

# Catalog matches Cursor CLI `--model` values documented for the pinned agent binary.
CURSOR_SUBSCRIPTION_MODELS = [
    {"id": "auto", "label": "Auto", "default_reasoning_effort": None, "reasoning_efforts": []},
    {"id": "gpt-5", "label": "GPT-5", "default_reasoning_effort": None, "reasoning_efforts": []},
    {"id": "sonnet-4-thinking", "label": "Sonnet 4 Thinking", "default_reasoning_effort": None, "reasoning_efforts": []},
]

# Catalog matches Google Antigravity models supported in the runner.
ANTIGRAVITY_SUBSCRIPTION_MODELS = [
    {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "default_reasoning_effort": "medium", "reasoning_efforts": ["low", "medium", "high", "xhigh"]},
    {"id": "gemini-3.1-pro", "label": "Gemini 3.1 Pro", "default_reasoning_effort": "high", "reasoning_efforts": ["low", "medium", "high", "xhigh"]},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash Preview", "default_reasoning_effort": None, "reasoning_efforts": []},
]

_SUBSCRIPTION_CLI_TARGETS = frozenset(
    {
        ProviderTarget.CODEX_SUBSCRIPTION.value,
        ProviderTarget.GROK_SUBSCRIPTION.value,
        ProviderTarget.CURSOR_SUBSCRIPTION.value,
        ProviderTarget.ANTIGRAVITY_SUBSCRIPTION.value,
    }
)


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
    if isinstance(value, str):
        raw = value.strip()
        if not raw.isdigit() and not (raw.startswith("-") and raw[1:].isdigit()):
            raise _FieldsValidationError({field: "Must be an integer"})
        parsed = int(raw)
    elif isinstance(value, int):
        parsed = value
    else:
        raise _FieldsValidationError({field: "Must be an integer"})
    if parsed < minimum or (maximum is not None and parsed > maximum):
        limit = f" between {minimum} and {maximum}" if maximum is not None else f" at least {minimum}"
        raise _FieldsValidationError({field: f"Must be{limit}"})
    return parsed


def _provider_surface_guard(request, *, admin: bool = False) -> JsonResponse | None:
    if os.getenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "").strip().lower() not in {"1", "true", "yes"}:
        return _error("Subscription CLI providers are disabled", 404, code="feature_disabled")
    if not user_can_manage_ai_routing(request.user):
        return _error("AI connection access is reserved for platform settings administrators", 403, code="permission_denied")
    feature = "ai_connections_admin" if admin else "ai_connections_personal"
    if not user_can_feature(request.user, feature, request=request):
        return _error("AI connection access is not granted", 403, code="permission_denied")
    return None


def _can_admin_ai_connections(user, *, request=None) -> bool:
    return user_can_feature(user, "ai_connections_admin", request=request)


def _can_manage_connection_grants(user, connection: AIProviderConnection, *, request=None) -> bool:
    """Admins, personal owners, or original creators can share a connection."""
    if _can_admin_ai_connections(user, request=request):
        return True
    if connection.owner_id == user.pk:
        return True
    if connection.created_by_id == user.pk:
        return True
    return False


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
        # Keep share/manage UI after personal→workspace promote (owner cleared, created_by remains).
        "manageable": _can_manage_connection_grants(user, connection),
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
    }
    if include_grants and _can_manage_connection_grants(user, connection):
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
        "max_slots": grant.max_slots,
    }


def _parse_grant_max_slots(data: dict[str, Any]) -> int | None:
    """null/omitted/0 => unlimited; otherwise 1..8."""
    if "max_slots" not in data or data.get("max_slots") in (None, "", 0, "0"):
        return None
    return _strict_int(data.get("max_slots"), field="max_slots", minimum=1, maximum=8)


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
    return candidates.filter(
        models.Q(owner=user) | models.Q(created_by=user) | models.Q(pk__in=allowed_ids)
    )


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
                {
                    "id": ProviderTarget.CURSOR_SUBSCRIPTION.value,
                    "label": "Cursor CLI (Cursor subscription)",
                    "auth": "browser",
                    "kind": "subscription_cli",
                },
                *[
                    {"id": target.value, "label": target.value, "kind": "platform"}
                    for target in ProviderTarget
                    if target
                    not in {
                        ProviderTarget.CODEX_SUBSCRIPTION,
                        ProviderTarget.GROK_SUBSCRIPTION,
                        ProviderTarget.CURSOR_SUBSCRIPTION,
                        ProviderTarget.ANTIGRAVITY_SUBSCRIPTION,
                    }
                ],
            ],
            "purposes": [item[0] for item in AIProviderPreference.PURPOSE_CHOICES],
            "scopes": [item[0] for item in AIProviderConnection.SCOPE_CHOICES],
            "models_by_target": {
                ProviderTarget.CODEX_SUBSCRIPTION.value: CODEX_SUBSCRIPTION_MODELS,
                ProviderTarget.GROK_SUBSCRIPTION.value: [],
                ProviderTarget.CURSOR_SUBSCRIPTION.value: CURSOR_SUBSCRIPTION_MODELS,
                ProviderTarget.ANTIGRAVITY_SUBSCRIPTION.value: ANTIGRAVITY_SUBSCRIPTION_MODELS,
            },
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
    if target_id not in _SUBSCRIPTION_CLI_TARGETS:
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
    if _can_manage_connection_grants(request.user, connection, request=request):
        return connection
    return _error("Connection is not manageable", 403, code="permission_denied")


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
        connection_id = connection.pk
        target_id = connection.target_id
        scope = connection.scope
        connection.delete()
        _audit_provider_mutation(
            request,
            action="ai_provider.connection.revoke",
            entity_type="ai_provider_connection",
            entity_id=connection_id,
            target_id=target_id,
            scope=scope,
        )
        return JsonResponse({"success": True, "revoked": True, "deleted": True})
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
    if "scope" in data:
        new_scope = str(data.get("scope") or "").strip()
        if new_scope not in {AIProviderConnection.SCOPE_PERSONAL, AIProviderConnection.SCOPE_WORKSPACE}:
            return _validation_error({"scope": "Must be personal or workspace"})
        if new_scope != connection.scope:
            if not _can_admin_ai_connections(request.user, request=request):
                return _error("Only AI connection admins can change scope", 403, code="permission_denied")
            try:
                with transaction.atomic():
                    if new_scope == AIProviderConnection.SCOPE_WORKSPACE:
                        previous_owner_id = connection.owner_id
                        connection.scope = AIProviderConnection.SCOPE_WORKSPACE
                        connection.owner = None
                        connection.save()
                        # Keep former owner usable until explicit grants are managed.
                        if previous_owner_id:
                            AIProviderConnectionGrant.objects.update_or_create(
                                connection=connection,
                                user_id=previous_owner_id,
                                defaults={
                                    "allow_interactive": True,
                                    "allow_unattended": True,
                                    "max_slots": None,
                                },
                            )
                    else:
                        connection.scope = AIProviderConnection.SCOPE_PERSONAL
                        connection.owner = request.user
                        connection.save()
                        AIProviderPoolMember.objects.filter(connection=connection).delete()
                        connection.grants.all().delete()
            except IntegrityError as exc:
                return _error(f"Could not change connection scope: {exc}", 409, code="conflict")
            _audit_provider_mutation(
                request,
                action="ai_provider.connection.scope_change",
                entity_type="ai_provider_connection",
                entity_id=connection.pk,
                target_id=connection.target_id,
                scope=connection.scope,
            )
            return JsonResponse(
                {"success": True, "connection": _serialize_connection(connection, request.user, include_grants=True)}
            )
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
    target_id = getattr(flow.connection, "target_id", "") if getattr(flow, "connection", None) else ""
    accepts_authorization_code = (
        flow.status == AIConnectionAuthFlow.STATUS_PENDING
        and target_id == "antigravity_subscription"
        and bool(flow.verification_uri)
    )
    link_ttl_seconds = 600 if accepts_authorization_code else None
    return {
        "id": str(flow.public_id),
        "connection_id": flow.connection_id,
        "status": flow.status,
        "verification_uri": flow.verification_uri,
        "user_code": flow.user_code,
        "oauth_state": flow.user_code if accepts_authorization_code else "",
        "error_code": flow.error_code,
        "expires_at": flow.expires_at.isoformat() if flow.expires_at else None,
        "created_at": flow.created_at.isoformat(),
        "completed_at": flow.completed_at.isoformat() if flow.completed_at else None,
        "target_id": target_id,
        "accepts_authorization_code": accepts_authorization_code,
        "link_expires_in": link_ttl_seconds,
    }


@login_required
@require_http_methods(["GET"])
def api_ai_provider_auth_flow(request, flow_id):
    if denied := _provider_surface_guard(request):
        return denied
    flow = get_object_or_404(AIConnectionAuthFlow.objects.select_related("connection"), public_id=flow_id)
    if not _can_manage_connection_grants(request.user, flow.connection, request=request):
        return _error("Auth flow is not accessible", 403, code="permission_denied")
    return JsonResponse({"success": True, "auth_flow": _serialize_auth_flow(flow)})


@login_required
@require_http_methods(["POST"])
def api_ai_provider_auth_flow_authorization_code(request, flow_id):
    if denied := _provider_surface_guard(request):
        return denied
    flow = get_object_or_404(AIConnectionAuthFlow.objects.select_related("connection"), public_id=flow_id)
    if not _can_manage_connection_grants(request.user, flow.connection, request=request):
        return _error("Auth flow is not accessible", 403, code="permission_denied")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("Invalid JSON body", 400, code="invalid_json")
    if not isinstance(payload, dict):
        return _error("Invalid JSON body", 400, code="invalid_json")
    raw_code = payload.get("authorization_code")
    if not isinstance(raw_code, str):
        return _error("authorization_code is required", 400, code="provider_request_invalid")
    try:
        accepted = submit_authorization_code(flow, raw_code)
    except ProviderRuntimeError as exc:
        if exc.code in {
            "provider_auth_not_pending",
            "provider_auth_code_unsupported",
            "provider_auth_not_ready",
            "provider_request_invalid",
            "provider_auth_session_not_ready",
            "provider_auth_session_mismatch",
            "provider_auth_failed",
        }:
            return _error(str(exc), 409, code=exc.code)
        if exc.code in {"provider_runner_unavailable", "provider_transport_unavailable"}:
            return _error(
                "Sign-in session expired or the CLI runner is unavailable; open a new sign-in link and paste a fresh code",
                503,
                code=exc.code,
            )
        return _error(str(exc), 503, code=exc.code)
    except Exception:
        logger.exception(
            "AI provider auth code submit failed flow_id=%s error_type=unexpected",
            flow.pk,
        )
        return _error(
            "Sign-in session expired or the CLI runner is unavailable; open a new sign-in link and paste a fresh code",
            503,
            code="provider_transport_unavailable",
        )
    if not accepted:
        return _error(
            "Sign-in session expired; open the latest link and paste a fresh code",
            409,
            code="provider_auth_session_not_ready",
        )
    return JsonResponse({"success": True, "accepted": True}, status=202)


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
    if target_id not in _SUBSCRIPTION_CLI_TARGETS:
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
@require_http_methods(["GET"])
def api_ai_provider_principals(request):
    """Lightweight user/group directory for CLI access grants (no access-admin required)."""
    if denied := _provider_surface_guard(request):
        return denied
    users = [
        {"id": row.pk, "username": row.username}
        for row in User.objects.filter(is_active=True).order_by("username").only("id", "username")[:500]
    ]
    groups = [
        {"id": row.pk, "name": row.name}
        for row in Group.objects.order_by("name").only("id", "name")[:200]
    ]
    return JsonResponse({"success": True, "users": users, "groups": groups})


@login_required
@require_http_methods(["POST"])
def api_ai_provider_grants(request):
    if denied := _provider_surface_guard(request):
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
            "max_slots": _parse_grant_max_slots(data),
        }
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    connection = AIProviderConnection.objects.filter(pk=connection_id).first()
    if connection is None:
        return _validation_error({"connection_id": "Connection does not exist"})
    if connection.status == AIProviderConnection.STATUS_REVOKED:
        return _validation_error({"connection_id": "Connection is revoked"})
    if not _can_manage_connection_grants(request.user, connection, request=request):
        return _error("Connection grants are not manageable", 403, code="permission_denied")
    if principal_name == "project_id" and not _can_admin_ai_connections(request.user, request=request):
        return _error("Only AI connection admins can grant to projects", 403, code="permission_denied")

    # Sharing requires workspace ACL. Promote personal connections automatically.
    if connection.scope == AIProviderConnection.SCOPE_PERSONAL:
        previous_owner_id = connection.owner_id
        connection.scope = AIProviderConnection.SCOPE_WORKSPACE
        connection.owner = None
        connection.save(update_fields=["scope", "owner", "updated_at"])
        if previous_owner_id:
            AIProviderConnectionGrant.objects.update_or_create(
                connection=connection,
                user_id=previous_owner_id,
                defaults={
                    "allow_interactive": True,
                    "allow_unattended": True,
                    "max_slots": None,
                },
            )
        _audit_provider_mutation(
            request,
            action="ai_provider.connection.scope_change",
            entity_type="ai_provider_connection",
            entity_id=connection.pk,
            target_id=connection.target_id,
            scope=connection.scope,
        )
    elif connection.scope != AIProviderConnection.SCOPE_WORKSPACE:
        return _validation_error({"connection_id": "Connection cannot receive grants"})

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

    assigned_preferences: list[dict[str, Any]] = []
    assign_raw = data.get("assign_preferences")
    if assign_raw is not None:
        if principal_name != "user_id":
            return _validation_error({"assign_preferences": "Only user grants can assign preferences"})
        if not isinstance(assign_raw, dict):
            return _validation_error({"assign_preferences": "Must be an object"})
        try:
            purposes = _parse_preference_purposes(
                {"purposes": assign_raw.get("purposes") or ["assistant"]}
            )
            project_scoped = _strict_bool(
                assign_raw.get("project_scoped"),
                field="assign_preferences.project_scoped",
                default=True,
            )
        except ValueError as exc:
            return _error(str(exc))
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
        model_id = assign_raw.get("model_id")
        reasoning_effort = assign_raw.get("reasoning_effort")
        try:
            assigned_preferences = _assign_connection_preferences(
                request,
                connection=connection,
                target_user=user,
                purposes=purposes,
                project_scoped=project_scoped,
                model_id=str(model_id) if model_id else None,
                reasoning_effort=str(reasoning_effort) if reasoning_effort else None,
            )
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)

    payload: dict[str, Any] = {"success": True, "grant": _serialize_grant(grant)}
    if assigned_preferences:
        payload["assigned_preferences"] = assigned_preferences
    return JsonResponse(payload, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def api_ai_provider_grant_detail(request, grant_id: int):
    if denied := _provider_surface_guard(request):
        return denied
    grant = get_object_or_404(AIProviderConnectionGrant.objects.select_related("connection"), pk=grant_id)
    connection = grant.connection
    if not _can_manage_connection_grants(request.user, connection, request=request):
        return _error("Connection grants are not manageable", 403, code="permission_denied")
    if request.method == "DELETE":
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

    try:
        data = _body(request)
    except ValueError as exc:
        return _error(str(exc))
    try:
        if "allow_interactive" in data:
            grant.allow_interactive = _strict_bool(data.get("allow_interactive"), field="allow_interactive")
        if "allow_unattended" in data:
            grant.allow_unattended = _strict_bool(data.get("allow_unattended"), field="allow_unattended")
        if "max_slots" in data:
            grant.max_slots = _parse_grant_max_slots(data)
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    grant.save()
    return JsonResponse({"success": True, "grant": _serialize_grant(grant)})


def _json_payload(response: JsonResponse) -> dict[str, Any]:
    try:
        payload = json.loads(response.content.decode("utf-8") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
            "reasoning_effort": preference.reasoning_effort or None,
        },
    }


def _user_has_direct_connection_grant(connection: AIProviderConnection, user_id: int) -> bool:
    return connection.grants.filter(user_id=user_id).exists()


def _can_inspect_user_preferences(user, *, request=None) -> bool:
    if _can_admin_ai_connections(user, request=request):
        return True
    return AIProviderConnection.objects.filter(
        models.Q(owner=user) | models.Q(created_by=user),
    ).exclude(status=AIProviderConnection.STATUS_REVOKED).exists()


def _authorize_preference_assignment(
    request,
    *,
    binding: ProviderBinding,
    target_user: User,
) -> JsonResponse | None:
    """Managers may assign CLI bindings to grantees; platform API only for admins."""
    if binding.target_id in _SUBSCRIPTION_CLI_TARGETS:
        if binding.connection_id is None:
            return _error("CLI preference assignment requires a connection_id", 400)
        connection = AIProviderConnection.objects.filter(pk=binding.connection_id).first()
        if connection is None or connection.target_id != binding.target_id:
            return _error("Connection does not exist or targets another provider", 400)
        if not _can_manage_connection_grants(request.user, connection, request=request):
            return _error("Connection grants are not manageable", 403, code="permission_denied")
        if not _can_admin_ai_connections(request.user, request=request):
            if not _user_has_direct_connection_grant(connection, target_user.pk):
                return _error(
                    "Target user must already have a grant on this connection",
                    403,
                    code="permission_denied",
                )
        return None
    if not _can_admin_ai_connections(request.user, request=request):
        return _error(
            "Only AI connection admins can assign platform API preferences",
            403,
            code="permission_denied",
        )
    return None


def _parse_preference_purposes(data: dict[str, Any]) -> list[str]:
    allowed = {item[0] for item in AIProviderPreference.PURPOSE_CHOICES}
    raw_purposes = data.get("purposes")
    if raw_purposes is not None:
        if not isinstance(raw_purposes, list) or not raw_purposes:
            raise _FieldsValidationError({"purposes": "Must be a non-empty list of purposes"})
        purposes: list[str] = []
        for item in raw_purposes:
            purpose = str(item or "")
            if purpose not in allowed:
                raise _FieldsValidationError({"purposes": f"Unknown preference purpose: {purpose}"})
            if purpose not in purposes:
                purposes.append(purpose)
        return purposes
    purpose = str(data.get("purpose") or "")
    if purpose not in allowed:
        raise ValueError("Unknown preference purpose")
    return [purpose]


def _upsert_preference_for_user(
    request,
    *,
    data: dict[str, Any],
    target_user: User | None,
    project_id: int | None,
    purpose: str,
    workspace_default: bool,
    assigned: bool,
) -> JsonResponse:
    filters = {
        "user": None if workspace_default else target_user,
        "project_id": project_id,
        "purpose": purpose,
    }
    response = _save_preference(
        request,
        data=data,
        filters=filters,
        workspace_default=workspace_default,
        project_id=project_id,
        access_user=None if workspace_default else target_user,
        skip_access_check=assigned and workspace_default is False,
    )
    if assigned and response.status_code < 400:
        preference_id = (_json_payload(response).get("preference") or {}).get("id")
        if preference_id:
            _audit_provider_mutation(
                request,
                action="ai_provider.preference.assign",
                entity_type="ai_provider_preference",
                entity_id=preference_id,
                target_id=str((data.get("binding") or {}).get("target_id") or ""),
                scope="assigned",
            )
    return response


def _assign_connection_preferences(
    request,
    *,
    connection: AIProviderConnection,
    target_user: User,
    purposes: list[str],
    project_scoped: bool,
    model_id: str | None = None,
    reasoning_effort: str | None = None,
) -> list[dict[str, Any]]:
    project_id = _active_project_id(request.user) if project_scoped else None
    binding_payload: dict[str, Any] = {
        "target_id": connection.target_id,
        "connection_id": connection.pk,
    }
    if model_id:
        binding_payload["model_id"] = model_id
    if reasoning_effort:
        binding_payload["reasoning_effort"] = reasoning_effort
    saved: list[dict[str, Any]] = []
    for purpose in purposes:
        response = _upsert_preference_for_user(
            request,
            data={
                "binding": binding_payload,
                "require_unattended": purpose in {"agents", "internal"},
            },
            target_user=target_user,
            project_id=project_id,
            purpose=purpose,
            workspace_default=False,
            assigned=True,
        )
        if response.status_code >= 400:
            raise _FieldsValidationError({"assign_preferences": _json_payload(response).get("error") or "assign failed"})
        saved.append(_json_payload(response)["preference"])
    return saved


def _save_preference(
    request,
    *,
    data: dict[str, Any],
    filters: dict[str, Any],
    workspace_default: bool,
    project_id: int | None,
    access_user=None,
    skip_access_check: bool = False,
) -> JsonResponse:
    try:
        binding = ProviderBinding.from_dict(data.get("binding") or {})
    except ValueError as exc:
        return _error(str(exc))
    if binding.target_id == ProviderTarget.CODEX_SUBSCRIPTION.value:
        model = next((item for item in CODEX_SUBSCRIPTION_MODELS if item["id"] == binding.model_id), None)
        if binding.model_id and model is None:
            return _error("Unknown Codex subscription model")
        if binding.reasoning_effort:
            supported = model["reasoning_efforts"] if model else CODEX_SUBSCRIPTION_MODELS[0]["reasoning_efforts"]
            if binding.reasoning_effort not in supported:
                return _error("Reasoning effort is not supported by the selected Codex model")
    elif binding.target_id == ProviderTarget.CURSOR_SUBSCRIPTION.value:
        model = next((item for item in CURSOR_SUBSCRIPTION_MODELS if item["id"] == binding.model_id), None)
        if binding.model_id and model is None:
            return _error("Unknown Cursor subscription model")
        # Cursor CLI has no reasoning_effort; ignore any value from older clients/UI.
        if binding.reasoning_effort:
            binding = replace(binding, reasoning_effort=None)
    elif binding.target_id == ProviderTarget.ANTIGRAVITY_SUBSCRIPTION.value:
        model = next((item for item in ANTIGRAVITY_SUBSCRIPTION_MODELS if item["id"] == binding.model_id), None)
        if binding.model_id and model is None:
            return _error("Unknown Antigravity subscription model")
        if binding.reasoning_effort:
            supported = model["reasoning_efforts"] if model else ANTIGRAVITY_SUBSCRIPTION_MODELS[0]["reasoning_efforts"]
            if binding.reasoning_effort not in supported:
                return _error("Reasoning effort is not supported by the selected Antigravity model")
    elif binding.reasoning_effort:
        return _error("Reasoning effort is currently supported only for Codex and Antigravity subscriptions")
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
    if not workspace_default and not skip_access_check:
        try:
            require_unattended = _strict_bool(data.get("require_unattended"), field="require_unattended", default=False)
        except _FieldsValidationError as exc:
            return _validation_error(exc.fields)
        mode = ExecutionMode.UNATTENDED if require_unattended else ExecutionMode.INTERACTIVE
        subject = access_user if access_user is not None else request.user
        decision = can_use_binding(binding, user_id=subject.pk, project_id=project_id, mode=mode)
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
        "reasoning_effort": binding.reasoning_effort or "",
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
        for_user_raw = request.GET.get("for_user_id")
        if for_user_raw not in (None, ""):
            try:
                for_user_id = _strict_int(for_user_raw, field="for_user_id", minimum=1)
            except _FieldsValidationError as exc:
                return _validation_error(exc.fields)
            if not _can_inspect_user_preferences(request.user, request=request):
                return _error("Preference inspection is not allowed", 403, code="permission_denied")
            target_user = User.objects.filter(pk=for_user_id, is_active=True).first()
            if target_user is None:
                return _validation_error({"for_user_id": "User does not exist"})
            scope_filter = models.Q(project__isnull=True)
            if project_id:
                scope_filter |= models.Q(project_id=project_id)
            rows = list(
                AIProviderPreference.objects.filter(scope_filter, user=target_user).select_related("connection", "pool")
            )
            return JsonResponse(
                {
                    "success": True,
                    "preferences": [_serialize_preference(item) for item in rows],
                    "workspace_defaults": [],
                    "for_user_id": target_user.pk,
                }
            )
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
    except ValueError as exc:
        return _error(str(exc))
    try:
        purposes = _parse_preference_purposes(data)
        workspace_default = _strict_bool(data.get("workspace_default"), field="workspace_default", default=False)
        project_scoped = _strict_bool(data.get("project_scoped"), field="project_scoped", default=True)
        target_user_id = data.get("target_user_id")
        if target_user_id is not None:
            target_user_id = _strict_int(target_user_id, field="target_user_id", minimum=1)
    except ValueError as exc:
        return _error(str(exc))
    except _FieldsValidationError as exc:
        return _validation_error(exc.fields)
    if workspace_default and target_user_id is not None:
        return _error("workspace_default cannot be combined with target_user_id")
    if workspace_default and (denied := _provider_surface_guard(request, admin=True)):
        return denied
    preference_project_id = project_id if project_scoped else None
    if workspace_default and preference_project_id is None:
        return _error("An active project is required for a workspace default")

    target_user = request.user
    assigned = False
    if target_user_id is not None:
        target_user = User.objects.filter(pk=target_user_id, is_active=True).first()
        if target_user is None:
            return _validation_error({"target_user_id": "User does not exist"})
        assigned = True
        try:
            binding = ProviderBinding.from_dict(data.get("binding") or {})
        except ValueError as exc:
            return _error(str(exc))
        if request.method != "DELETE":
            denied_assign = _authorize_preference_assignment(request, binding=binding, target_user=target_user)
            if denied_assign is not None:
                return denied_assign
        else:
            if not _can_inspect_user_preferences(request.user, request=request):
                return _error("Preference assignment is not allowed", 403, code="permission_denied")

    if request.method == "DELETE":
        deleted_ids: list[int] = []
        for purpose in purposes:
            filters = {
                "user": None if workspace_default else target_user,
                "project_id": preference_project_id,
                "purpose": purpose,
            }
            deleted_ids.extend(list(AIProviderPreference.objects.filter(**filters).values_list("pk", flat=True)))
            AIProviderPreference.objects.filter(**filters).delete()
        if workspace_default:
            for preference_id in deleted_ids:
                _audit_provider_mutation(
                    request,
                    action="ai_provider.workspace_default.delete",
                    entity_type="ai_provider_preference",
                    entity_id=preference_id,
                    scope="workspace",
                )
        elif assigned:
            for preference_id in deleted_ids:
                _audit_provider_mutation(
                    request,
                    action="ai_provider.preference.assign_clear",
                    entity_type="ai_provider_preference",
                    entity_id=preference_id,
                    scope="assigned",
                )
        return JsonResponse({"success": True, "deleted": len(deleted_ids)})

    saved: list[dict[str, Any]] = []
    for purpose in purposes:
        response = _upsert_preference_for_user(
            request,
            data=data,
            target_user=None if workspace_default else target_user,
            project_id=preference_project_id,
            purpose=purpose,
            workspace_default=workspace_default,
            assigned=assigned,
        )
        if response.status_code >= 400:
            return response
        saved.append(_json_payload(response)["preference"])
    if len(saved) == 1:
        return JsonResponse({"success": True, "preference": saved[0]})
    return JsonResponse({"success": True, "preferences": saved})
