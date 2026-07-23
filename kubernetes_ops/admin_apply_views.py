from __future__ import annotations

import json
from typing import Any

import yaml
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent
from kubernetes_ops.services.admin_apply import apply_kubernetes_resource
from kubernetes_ops.services.admin_resources import AdminResourceError


def _json_body(request) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
    if not isinstance(data, dict):
        return {}, JsonResponse({"success": False, "error": "JSON body must be an object"}, status=400)
    return data, None


def _manifest_from_body(data: dict[str, Any]) -> tuple[dict[str, Any], JsonResponse | None]:
    manifest = data.get("manifest")
    if isinstance(manifest, dict):
        return manifest, None
    try:
        parsed = yaml.safe_load(str(data.get("manifest_yaml") or "").strip())
    except yaml.YAMLError as exc:
        return {}, JsonResponse(
            {
                "success": False,
                "error": "Manifest YAML is invalid.",
                "code": "manifest_yaml_invalid",
                "payload": {"detail": str(exc)[:500]},
            },
            status=400,
        )
    if not isinstance(parsed, dict):
        return {}, JsonResponse(
            {"success": False, "error": "Manifest must be a Kubernetes object.", "code": "manifest_object_required"},
            status=400,
        )
    return parsed, None


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes admin apply API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _error_response(error: AdminResourceError) -> JsonResponse:
    return JsonResponse(
        {
            "success": False,
            "error": str(error),
            "code": error.code,
            "payload": error.payload,
        },
        status=error.status,
    )


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_admin_apply(request, cluster_id: str):
    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        manifest, manifest_error = _manifest_from_body(data)
        if manifest_error:
            return manifest_error
        try:
            payload = apply_kubernetes_resource(
                user=request.user,
                session_id=str(data.get("session_id") or ""),
                cluster_id=cluster_id,
                dry_run_action_id=str(data.get("dry_run_action_id") or ""),
                reason=str(data.get("reason") or ""),
                manifest=manifest,
                namespace=str(data.get("namespace") or ""),
                resource=str(data.get("resource") or ""),
            )
        except AdminResourceError as exc:
            _audit(
                request,
                "k8s.admin_resource.apply_rejected",
                payload={"code": exc.code, "cluster_id": cluster_id},
                session_id=str(data.get("session_id") or ""),
            )
            return _error_response(exc)
        _audit(
            request,
            "k8s.admin_resource.apply",
            payload={
                "cluster_id": cluster_id,
                "target": payload["target"],
                "redacted": bool(payload.get("redacted")),
                "dry_run_action_id": payload.get("dry_run_proof", {}).get("id", ""),
                "action_id": payload.get("action", {}).get("id", ""),
            },
            session_id=str(data.get("session_id") or ""),
        )
        return JsonResponse(payload)

    return _safe_json(handler)


def _audit(request, action: str, *, payload: dict[str, Any], session_id: str) -> None:
    session = _session_for_audit(session_id)
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider="webterm",
        cluster=session.cluster if session and session.cluster_id else None,
        payload={"session_id": str(session.session_id) if session else session_id[:80], **payload},
    )


def _session_for_audit(session_id: str) -> K8sAdminSession | None:
    if not session_id:
        return None
    try:
        return K8sAdminSession.objects.select_related("cluster").filter(session_id=session_id).first()
    except (TypeError, ValueError, ValidationError):
        return None
