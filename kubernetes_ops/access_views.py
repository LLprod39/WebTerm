"""Admin APIs for granting cluster / namespace access to users."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from kubernetes_ops.models import K8sAuditEvent, K8sClusterAccess, K8sNamespace
from kubernetes_ops.services.access import serialize_access_grant
from kubernetes_ops.views_helpers import _cluster_or_none, _json_body, _staff_required


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes access API failed: %s", exc)
        return internal_error_response(None, exc)


def _parse_expires_at(raw_value):
    if raw_value in (None, "", "null", "None"):
        return None
    dt = parse_datetime(str(raw_value))
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _resolve_user(identifier: str) -> User | None:
    value = str(identifier or "").strip()
    if not value:
        return None
    if value.isdigit():
        user = User.objects.filter(id=int(value)).first()
        if user:
            return user
    return User.objects.filter(username=value).first() or User.objects.filter(email=value).first()


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET", "POST"])
def api_kubernetes_cluster_access(request, cluster_id: str):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)

        if request.method == "GET":
            grants = (
                K8sClusterAccess.objects.select_related("user", "granted_by", "cluster")
                .filter(cluster=cluster, is_revoked=False)
                .order_by("-created_at")
            )
            return JsonResponse(
                {"success": True, "grants": [serialize_access_grant(item) for item in grants]}
            )

        data, error_response = _json_body(request)
        if error_response:
            return error_response
        target = _resolve_user(str(data.get("user") or ""))
        if target is None:
            return JsonResponse({"success": False, "error": "User not found"}, status=404)
        if target.id == request.user.id:
            return JsonResponse({"success": False, "error": "Cannot grant access to yourself"}, status=400)

        namespaces_raw = data.get("namespaces") or []
        if namespaces_raw in ("", None):
            namespaces_raw = []
        if not isinstance(namespaces_raw, list):
            return JsonResponse({"success": False, "error": "namespaces must be a list"}, status=400)
        namespaces = [str(item).strip() for item in namespaces_raw if str(item).strip()]
        if namespaces:
            known = set(
                K8sNamespace.objects.filter(cluster=cluster, name__in=namespaces).values_list("name", flat=True)
            )
            unknown = [name for name in namespaces if name not in known]
            if unknown:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Unknown namespaces for this cluster: {', '.join(unknown[:8])}",
                    },
                    status=400,
                )

        raw_expires = data.get("expires_at")
        expires_at = _parse_expires_at(raw_expires)
        if raw_expires not in (None, "", "null", "None") and not expires_at:
            return JsonResponse({"success": False, "error": "Invalid expires_at format"}, status=400)
        if expires_at and expires_at <= timezone.now():
            return JsonResponse({"success": False, "error": "expires_at must be in the future"}, status=400)

        can_view_logs = bool(data.get("can_view_logs", True))
        can_exec = bool(data.get("can_exec", False))

        grant, _ = K8sClusterAccess.objects.update_or_create(
            cluster=cluster,
            user=target,
            defaults={
                "granted_by": request.user,
                "namespaces": namespaces,
                "can_view_logs": can_view_logs,
                "can_exec": can_exec,
                "expires_at": expires_at,
                "is_revoked": False,
                "revoked_at": None,
            },
        )
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.access.grant",
            cluster=cluster,
            payload={
                "grant_id": grant.id,
                "user_id": target.id,
                "namespaces": namespaces,
                "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
            },
        )
        return JsonResponse({"success": True, "grant": serialize_access_grant(grant)}, status=201)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_cluster_access_revoke(request, cluster_id: str, grant_id: int):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        grant = K8sClusterAccess.objects.filter(id=grant_id, cluster=cluster).first()
        if grant is None:
            return JsonResponse({"success": False, "error": "Grant not found"}, status=404)
        grant.is_revoked = True
        grant.revoked_at = timezone.now()
        grant.save(update_fields=["is_revoked", "revoked_at", "updated_at"])
        K8sAuditEvent.objects.create(
            user=request.user,
            username_snapshot=getattr(request.user, "username", ""),
            action="k8s.access.revoke",
            cluster=cluster,
            payload={"grant_id": grant.id, "user_id": grant.user_id},
        )
        return JsonResponse({"success": True, "grant": serialize_access_grant(grant)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET"])
def api_kubernetes_access_candidates(request):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        query = str(request.GET.get("q") or "").strip()
        users = User.objects.filter(is_active=True).order_by("username")
        if query:
            users = users.filter(
                Q(username__icontains=query) | Q(email__icontains=query) | Q(first_name__icontains=query)
            )
        users = users[:30]
        return JsonResponse(
            {
                "success": True,
                "candidates": [
                    {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email or "",
                        "is_staff": bool(user.is_staff),
                    }
                    for user in users
                ],
            }
        )

    return _safe_json(handler)
