"""Self-service kubeconfig connection API."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from loguru import logger

from core_ui.api_errors import internal_error_response
from core_ui.decorators import require_feature
from core_ui.managed_secrets import delete_kubernetes_provider_token
from kubernetes_ops.models import K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy
from kubernetes_ops.serializers import serialize_provider
from kubernetes_ops.services.access import cluster_access_origin, visible_clusters_queryset
from kubernetes_ops.services.kubeconfig import (
    materialize_connection_cluster,
    parse_kubeconfig_text,
    probe_kubeconfig_provider,
    provider_scope_for_user,
    select_context,
    sync_kubeconfig_provider,
)
from kubernetes_ops.services.secrets import managed_provider_secret_ref
from kubernetes_ops.views_helpers import (
    _apply_provider_secret_value,
    _as_bool,
    _json_body,
    _user_owns_provider,
)


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes kubeconfig connection API failed: %s", exc)
        return internal_error_response(None, exc)


def _audit(request, action: str, *, provider: str = "", cluster: K8sCluster | None = None, payload: dict | None = None):
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider=provider,
        cluster=cluster,
        payload=payload or {},
    )


def _connection_payload(provider: K8sProvider, *, user) -> dict:
    labels = provider.labels if isinstance(provider.labels, dict) else {}
    cluster = K8sCluster.objects.filter(rancher_cluster_id=f"kubeconfig:{provider.id}").first()
    probe_hint = {
        "context": str(labels.get("context") or ""),
        "server": provider.base_url or str(labels.get("server") or ""),
        "contexts": list(labels.get("available_contexts") or []),
    }
    return {
        "id": provider.id,
        "name": provider.name,
        "kind": provider.kind,
        "scope": provider.scope,
        "enabled": provider.enabled,
        "has_secret": bool(provider.secret_ref),
        "context": probe_hint["context"],
        "server": probe_hint["server"],
        "available_contexts": probe_hint["contexts"],
        "cluster_id": f"cluster_{cluster.id}" if cluster else None,
        "cluster_name": cluster.name if cluster else None,
        "access_origin": cluster_access_origin(user, cluster) if cluster else "owned",
        "last_sync_at": provider.last_sync_at.isoformat() if provider.last_sync_at else None,
        "last_error": provider.last_error,
        "provider": serialize_provider(provider, user=user),
    }


def _can_manage_connection(request, provider: K8sProvider) -> JsonResponse | None:
    if getattr(request.user, "is_staff", False):
        return None
    if provider.kind != K8sProvider.KIND_KUBECONFIG:
        return JsonResponse(
            {"success": False, "error": "Not a kubeconfig connection.", "code": "invalid_kind"},
            status=400,
        )
    if provider.scope == K8sProvider.SCOPE_PLATFORM:
        return JsonResponse(
            {"success": False, "error": "Platform connections are admin-only.", "code": "admin_required"},
            status=403,
        )
    if not _user_owns_provider(request.user, provider):
        return JsonResponse(
            {"success": False, "error": "You can only manage your own connections.", "code": "owner_required"},
            status=403,
        )
    return None


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET"])
def api_kubernetes_connections(request):
    def handler():
        policy = kubernetes_permission_policy(request.user)
        if not policy.get("can_connect_clusters"):
            return JsonResponse(
                {"success": False, "error": "Cluster connections are not allowed.", "code": "forbidden"},
                status=403,
            )
        qs = K8sProvider.objects.filter(kind=K8sProvider.KIND_KUBECONFIG)
        if not getattr(request.user, "is_staff", False):
            qs = qs.filter(created_by=request.user, scope=K8sProvider.SCOPE_PERSONAL)
        connections = [_connection_payload(item, user=request.user) for item in qs.order_by("-updated_at")]

        granted = []
        for cluster in visible_clusters_queryset(request.user):
            origin = cluster_access_origin(request.user, cluster)
            if origin == "granted":
                granted.append(
                    {
                        "cluster_id": f"cluster_{cluster.id}",
                        "cluster_name": cluster.name,
                        "access_origin": "granted",
                        "environment": cluster.environment,
                        "health": cluster.health,
                    }
                )

        return JsonResponse({"success": True, "connections": connections, "granted_clusters": granted})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_connections_kubeconfig(request):
    def handler():
        policy = kubernetes_permission_policy(request.user)
        if not policy.get("can_connect_clusters"):
            return JsonResponse(
                {"success": False, "error": "Cluster connections are not allowed.", "code": "forbidden"},
                status=403,
            )
        data, error_response = _json_body(request)
        if error_response:
            return error_response

        kubeconfig = str(data.get("kubeconfig") or data.get("secret_value") or "").strip()
        if not kubeconfig:
            return JsonResponse({"success": False, "error": "kubeconfig text is required."}, status=400)

        try:
            parsed = parse_kubeconfig_text(kubeconfig)
            context = select_context(parsed, str(data.get("context") or ""))
            scope = provider_scope_for_user(
                is_staff=bool(getattr(request.user, "is_staff", False)),
                requested=str(data.get("scope") or ""),
            )
        except ValueError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

        name = str(data.get("name") or "").strip() or f"{context.name}"
        name = name[:120]
        if K8sProvider.objects.filter(kind=K8sProvider.KIND_KUBECONFIG, name=name).exists():
            name = f"{name}-{request.user.id}"[:120]

        labels = {
            "source": "kubeconfig",
            "context": context.name,
            "server": context.server,
            "available_contexts": [item.name for item in parsed.contexts],
        }
        if data.get("cluster_display_name"):
            labels["cluster_display_name"] = str(data.get("cluster_display_name"))[:120]

        provider = K8sProvider.objects.create(
            name=name,
            kind=K8sProvider.KIND_KUBECONFIG,
            base_url=context.server,
            enabled=True,
            auth_mode=K8sProvider.AUTH_SECRET_REF,
            secret_ref="",
            scope=scope,
            labels=labels,
            created_by=request.user,
        )
        _apply_provider_secret_value(provider, kubeconfig)
        provider.secret_ref = managed_provider_secret_ref(provider.id)
        provider.save(update_fields=["secret_ref", "updated_at"])

        sync_now = _as_bool(data.get("sync"), True)
        sync_result = None
        cluster = None
        if sync_now:
            sync_result = sync_kubeconfig_provider(provider, dry_run=False)
            cluster = K8sCluster.objects.filter(rancher_cluster_id=f"kubeconfig:{provider.id}").first()
        else:
            cluster = materialize_connection_cluster(provider, context)

        _audit(
            request,
            "k8s.connection.kubeconfig.create",
            provider=provider.name,
            cluster=cluster,
            payload={
                "provider_id": provider.id,
                "scope": provider.scope,
                "context": context.name,
                "synced": bool(sync_result and sync_result.success),
            },
        )

        # Never echo kubeconfig back.
        response = {
            "success": True,
            "connection": _connection_payload(provider, user=request.user),
        }
        if sync_result is not None:
            response["sync"] = {
                "success": sync_result.success,
                "namespaces": sync_result.namespaces,
                "pods": sync_result.pods,
                "error": sync_result.error,
            }
            if not sync_result.success:
                response["success"] = False
        return JsonResponse(response, status=201 if response["success"] else 200)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_connection_probe(request, connection_id: int):
    def handler():
        provider = K8sProvider.objects.filter(id=connection_id, kind=K8sProvider.KIND_KUBECONFIG).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Connection not found"}, status=404)
        denied = _can_manage_connection(request, provider)
        if denied:
            return denied
        result = probe_kubeconfig_provider(provider)
        _audit(
            request,
            "k8s.connection.kubeconfig.probe",
            provider=provider.name,
            payload={"provider_id": provider.id, "success": result.success, "status": result.status},
        )
        return JsonResponse(
            {
                "success": result.success,
                "probe": {
                    "success": result.success,
                    "status": result.status,
                    "server": result.server,
                    "context": result.context,
                    "namespace_count": result.namespace_count,
                    "duration_ms": result.duration_ms,
                    "checked_at": result.checked_at,
                    "error": result.error,
                },
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_connection_rotate(request, connection_id: int):
    def handler():
        provider = K8sProvider.objects.filter(id=connection_id, kind=K8sProvider.KIND_KUBECONFIG).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Connection not found"}, status=404)
        denied = _can_manage_connection(request, provider)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        kubeconfig = str(data.get("kubeconfig") or data.get("secret_value") or "").strip()
        if not kubeconfig:
            return JsonResponse({"success": False, "error": "kubeconfig text is required."}, status=400)
        try:
            parsed = parse_kubeconfig_text(kubeconfig)
            labels = provider.labels if isinstance(provider.labels, dict) else {}
            context_name = str(data.get("context") or labels.get("context") or "")
            context = select_context(parsed, context_name)
        except ValueError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

        labels = dict(provider.labels) if isinstance(provider.labels, dict) else {}
        labels.update(
            {
                "source": "kubeconfig",
                "context": context.name,
                "server": context.server,
                "available_contexts": [item.name for item in parsed.contexts],
            }
        )
        provider.labels = labels
        provider.base_url = context.server
        provider.save(update_fields=["labels", "base_url", "updated_at"])
        _apply_provider_secret_value(provider, kubeconfig)
        sync_result = sync_kubeconfig_provider(provider, dry_run=False)
        _audit(
            request,
            "k8s.connection.kubeconfig.rotate",
            provider=provider.name,
            payload={"provider_id": provider.id, "synced": sync_result.success},
        )
        return JsonResponse(
            {
                "success": sync_result.success,
                "connection": _connection_payload(provider, user=request.user),
                "sync": {
                    "success": sync_result.success,
                    "namespaces": sync_result.namespaces,
                    "pods": sync_result.pods,
                    "error": sync_result.error,
                },
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["DELETE"])
def api_kubernetes_connection_delete(request, connection_id: int):
    def handler():
        provider = K8sProvider.objects.filter(id=connection_id, kind=K8sProvider.KIND_KUBECONFIG).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Connection not found"}, status=404)
        denied = _can_manage_connection(request, provider)
        if denied:
            return denied
        payload = {"provider_id": provider.id, "name": provider.name, "scope": provider.scope}
        cluster = K8sCluster.objects.filter(rancher_cluster_id=f"kubeconfig:{provider.id}").first()
        delete_kubernetes_provider_token(provider.id)
        if cluster is not None:
            cluster.delete()
        provider.delete()
        _audit(request, "k8s.connection.kubeconfig.delete", provider=payload["name"], payload=payload)
        return JsonResponse({"success": True})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_connection_parse(request):
    """Preview contexts from kubeconfig without storing secrets."""

    def handler():
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        kubeconfig = str(data.get("kubeconfig") or "").strip()
        try:
            parsed = parse_kubeconfig_text(kubeconfig)
        except ValueError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        return JsonResponse(
            {
                "success": True,
                "current_context": parsed.current_context,
                "contexts": [
                    {
                        "name": item.name,
                        "server": item.server,
                        "cluster": item.cluster_name,
                        "namespace": item.namespace,
                    }
                    for item in parsed.contexts
                ],
            }
        )

    return _safe_json(handler)
