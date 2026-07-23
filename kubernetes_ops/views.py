from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods
from loguru import logger

from core_ui.decorators import require_feature
from core_ui.managed_secrets import delete_kubernetes_provider_token, set_kubernetes_provider_token
from kubernetes_ops.models import (
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_cluster_event,
    serialize_fleet_bundle,
    serialize_kubernetes_event,
    serialize_namespace,
    serialize_provider,
    serialize_workload,
)
from kubernetes_ops.services.overview import build_overview_payload
from kubernetes_ops.services.readiness import build_kubernetes_readiness_report
from kubernetes_ops.services.secrets import managed_provider_secret_ref
from kubernetes_ops.services.sync import KubernetesSyncResult, sync_kubernetes_providers


def _cluster_or_none(cluster_id: str) -> K8sCluster | None:
    value = str(cluster_id or "").strip()
    numeric = value.removeprefix("cluster_")
    query = Q(name=value) | Q(rancher_cluster_id=value) | Q(devtron_cluster_id=value)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


def _safe_json(handler):
    try:
        return handler()
    except Exception as exc:
        logger.exception("kubernetes ops API failed: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


def _staff_required(request) -> JsonResponse | None:
    if not getattr(request.user, "is_staff", False):
        return JsonResponse(
            {"success": False, "error": "Admin access is required.", "code": "admin_required"}, status=403
        )
    return None


def _json_body(request) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}, JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)
    if not isinstance(data, dict):
        return {}, JsonResponse({"success": False, "error": "JSON body must be an object"}, status=400)
    return data, None


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _validate_secret_ref(auth_mode: str, secret_ref: str) -> str | None:
    if auth_mode == K8sProvider.AUTH_NONE:
        return None
    if not secret_ref:
        return "secret_ref is required unless auth_mode is none."
    allowed_prefixes = (
        "env:",
        "vault://",
        "secret://",
        "k8s://",
        "aws-sm://",
        "gcp-sm://",
        "azure-kv://",
        "managed:kubernetes-provider-token:",
    )
    if not secret_ref.startswith(allowed_prefixes):
        return "secret_ref must be an external secret reference, not a raw token."
    return None


def _provider_payload_from_body(
    data: dict[str, Any], provider: K8sProvider | None = None
) -> tuple[dict[str, Any], str, str]:
    name = str(data.get("name", provider.name if provider else "") or "").strip()
    kind = str(data.get("kind", provider.kind if provider else "") or "").strip()
    base_url = str(data.get("base_url", provider.base_url if provider else "") or "").strip().rstrip("/")
    enabled = _as_bool(data.get("enabled"), provider.enabled if provider else True)
    auth_mode = str(
        data.get("auth_mode", provider.auth_mode if provider else K8sProvider.AUTH_SECRET_REF) or ""
    ).strip()
    secret_ref = str(data.get("secret_ref", provider.secret_ref if provider else "") or "").strip()
    secret_value = str(data.get("secret_value") or "").strip() if "secret_value" in data else ""
    labels = data.get("labels", provider.labels if provider else {})

    if not name:
        return {}, "", "name is required."
    if kind not in dict(K8sProvider.KIND_CHOICES):
        return {}, "", "kind must be rancher or devtron."
    if not base_url.startswith(("https://", "http://")):
        return {}, "", "base_url must start with http:// or https://."
    if auth_mode not in dict(K8sProvider.AUTH_CHOICES):
        return {}, "", "auth_mode is invalid."
    if not isinstance(labels, dict):
        return {}, "", "labels must be an object."
    if auth_mode == K8sProvider.AUTH_NONE and secret_value:
        return {}, "", "secret_value cannot be stored when auth_mode is none."
    if auth_mode == K8sProvider.AUTH_NONE:
        secret_ref = ""
    secret_error = (
        None if secret_value and auth_mode != K8sProvider.AUTH_NONE else _validate_secret_ref(auth_mode, secret_ref)
    )
    if secret_error:
        return {}, "", secret_error
    return (
        {
            "name": name,
            "kind": kind,
            "base_url": base_url,
            "enabled": enabled,
            "auth_mode": auth_mode,
            "secret_ref": secret_ref,
            "labels": labels,
        },
        secret_value,
        "",
    )


def _apply_provider_secret_value(provider: K8sProvider, secret_value: str) -> bool:
    if not secret_value:
        return False
    set_kubernetes_provider_token(provider.id, secret_value)
    provider.secret_ref = managed_provider_secret_ref(provider.id)
    provider.save(update_fields=["secret_ref", "updated_at"])
    return True


def _delete_managed_provider_secret_if_external(provider_id: int, old_ref: str, new_ref: str) -> None:
    if old_ref.startswith("managed:kubernetes-provider-token:") and old_ref != new_ref:
        delete_kubernetes_provider_token(provider_id)


def _sync_result_payload(result: KubernetesSyncResult) -> dict[str, Any]:
    return {
        "provider_id": result.provider_id,
        "provider_name": result.provider_name,
        "provider_kind": result.provider_kind,
        "success": result.success,
        "clusters": result.clusters,
        "namespaces": result.namespaces,
        "workloads": result.workloads,
        "pods": result.pods,
        "services": result.services,
        "ingresses": result.ingresses,
        "events": result.events,
        "apps": result.apps,
        "fleet_bundles": result.fleet_bundles,
        "error": result.error,
        "dry_run": result.dry_run,
    }


def _audit(
    request,
    action: str,
    *,
    provider: str = "",
    cluster: K8sCluster | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    K8sAuditEvent.objects.create(
        user=request.user,
        username_snapshot=getattr(request.user, "username", ""),
        action=action,
        provider=provider,
        cluster=cluster,
        payload=payload or {},
    )


def _namespace_summaries(cluster: K8sCluster, *, user=None) -> list[dict[str, Any]]:
    native_namespaces = list(K8sNamespace.objects.filter(cluster=cluster))
    if native_namespaces:
        return [serialize_namespace(namespace, user=user) for namespace in native_namespaces]

    rows = (
        K8sAppRef.objects.filter(cluster=cluster)
        .values("namespace", "environment")
        .annotate(
            apps=Count("id"),
            healthy=Count("id", filter=Q(health=K8sCluster.HEALTH_HEALTHY)),
            warning=Count("id", filter=Q(health=K8sCluster.HEALTH_WARNING)),
            degraded=Count("id", filter=Q(health=K8sCluster.HEALTH_DEGRADED)),
            unknown=Count("id", filter=Q(health=K8sCluster.HEALTH_UNKNOWN)),
            last_sync_at=Max("last_sync_at"),
        )
        .order_by("namespace")
    )
    summaries = []
    for row in rows:
        namespace_apps = K8sAppRef.objects.filter(cluster=cluster, namespace=row["namespace"])
        summaries.append(
            {
                "id": f"{cluster.id}:{row['namespace']}",
                "name": row["namespace"],
                "environment": row["environment"] or cluster.environment,
                "apps": int(row["apps"] or 0),
                "healthy": int(row["healthy"] or 0),
                "warning": int(row["warning"] or 0),
                "degraded": int(row["degraded"] or 0),
                "unknown": int(row["unknown"] or 0),
                "owners": sorted({item for item in namespace_apps.values_list("owner", flat=True) if item}),
                "teams": sorted({item for item in namespace_apps.values_list("team", flat=True) if item}),
                "last_sync_at": row["last_sync_at"].isoformat() if row["last_sync_at"] else None,
            }
        )
    return summaries


def _workload_rows(cluster: K8sCluster, *, user=None) -> list[dict[str, Any]]:
    native_workloads = list(K8sWorkloadRef.objects.filter(cluster=cluster).select_related("cluster"))
    if native_workloads:
        return [serialize_workload(workload, user=user) for workload in native_workloads]
    apps = K8sAppRef.objects.filter(cluster=cluster).select_related("cluster")
    return [serialize_app(app, user=user) for app in apps]


def _cluster_event_rows(cluster: K8sCluster) -> list[dict[str, Any]]:
    native_events = list(K8sEvent.objects.filter(cluster=cluster)[:100])
    if native_events:
        return [serialize_kubernetes_event(event) for event in native_events]
    audit_events = K8sAuditEvent.objects.filter(cluster=cluster).select_related("user", "cluster")[:100]
    return [serialize_cluster_event(event) for event in audit_events]


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_readiness(request):
    return _safe_json(lambda: JsonResponse(build_kubernetes_readiness_report(user=request.user)))


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_overview(request):
    return _safe_json(lambda: JsonResponse(build_overview_payload(user=request.user)))


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET", "POST"])
def api_kubernetes_providers(request):
    def handler():
        if request.method == "GET":
            denied = _staff_required(request)
            if denied:
                return denied
            return JsonResponse(
                {
                    "success": True,
                    "providers": [
                        serialize_provider(provider, user=request.user) for provider in K8sProvider.objects.all()
                    ],
                }
            )

        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        payload, secret_value, error = _provider_payload_from_body(data)
        if error:
            return JsonResponse({"success": False, "error": error}, status=400)
        if secret_value:
            payload["secret_ref"] = ""
        provider = K8sProvider.objects.create(**payload)
        managed_secret_created = _apply_provider_secret_value(provider, secret_value)
        _audit(
            request,
            "k8s.provider.create",
            provider=provider.name,
            payload={"provider_id": provider.id, "kind": provider.kind, "managed_secret": managed_secret_created},
        )
        return JsonResponse({"success": True, "provider": serialize_provider(provider, user=request.user)}, status=201)

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["GET", "PATCH", "POST", "DELETE"])
def api_kubernetes_provider_detail(request, provider_id: int):
    def handler():
        provider = K8sProvider.objects.filter(id=provider_id).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Provider not found"}, status=404)
        if request.method == "GET":
            denied = _staff_required(request)
            if denied:
                return denied
            return JsonResponse({"success": True, "provider": serialize_provider(provider, user=request.user)})
        denied = _staff_required(request)
        if denied:
            return denied
        if request.method == "DELETE":
            payload = {"provider_id": provider.id, "kind": provider.kind, "name": provider.name}
            delete_kubernetes_provider_token(provider.id)
            provider.delete()
            _audit(request, "k8s.provider.delete", provider=payload["name"], payload=payload)
            return JsonResponse({"success": True})
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        payload, secret_value, error = _provider_payload_from_body(data, provider)
        if error:
            return JsonResponse({"success": False, "error": error}, status=400)
        old_ref = provider.secret_ref
        if secret_value:
            payload["secret_ref"] = old_ref
        for field, value in payload.items():
            setattr(provider, field, value)
        provider.save()
        managed_secret_rotated = _apply_provider_secret_value(provider, secret_value)
        _delete_managed_provider_secret_if_external(provider.id, old_ref, provider.secret_ref)
        _audit(
            request,
            "k8s.provider.update",
            provider=provider.name,
            payload={
                "provider_id": provider.id,
                "kind": provider.kind,
                "managed_secret_rotated": managed_secret_rotated,
            },
        )
        return JsonResponse({"success": True, "provider": serialize_provider(provider, user=request.user)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_sync(request):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        dry_run = _as_bool(data.get("dry_run"), False)
        kind = str(data.get("kind") or "").strip()
        if kind and kind not in dict(K8sProvider.KIND_CHOICES):
            return JsonResponse({"success": False, "error": "kind must be rancher or devtron."}, status=400)
        results = sync_kubernetes_providers(kind=kind, dry_run=dry_run)
        _audit(request, "k8s.provider.sync_all", payload={"kind": kind, "dry_run": dry_run, "count": len(results)})
        failed = [item for item in results if not item.success]
        return JsonResponse({"success": not failed, "results": [_sync_result_payload(item) for item in results]})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_http_methods(["POST"])
def api_kubernetes_provider_sync(request, provider_id: int):
    def handler():
        denied = _staff_required(request)
        if denied:
            return denied
        data, error_response = _json_body(request)
        if error_response:
            return error_response
        dry_run = _as_bool(data.get("dry_run"), False)
        provider = K8sProvider.objects.filter(id=provider_id).first()
        if provider is None:
            return JsonResponse({"success": False, "error": "Provider not found"}, status=404)
        results = sync_kubernetes_providers(provider_id=provider.id, dry_run=dry_run)
        _audit(
            request,
            "k8s.provider.sync",
            provider=provider.name,
            payload={"provider_id": provider.id, "dry_run": dry_run},
        )
        failed = [item for item in results if not item.success]
        return JsonResponse({"success": not failed, "results": [_sync_result_payload(item) for item in results]})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_clusters(request):
    return _safe_json(
        lambda: JsonResponse(
            {
                "success": True,
                "clusters": [serialize_cluster(cluster, user=request.user) for cluster in K8sCluster.objects.all()],
            }
        )
    )


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_cluster_detail(request, cluster_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        return JsonResponse({"success": True, "cluster": serialize_cluster(cluster, user=request.user)})

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_cluster_namespaces(request, cluster_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        return JsonResponse(
            {
                "success": True,
                "cluster": serialize_cluster(cluster, user=request.user),
                "namespaces": _namespace_summaries(cluster, user=request.user),
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_cluster_workloads(request, cluster_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        return JsonResponse(
            {
                "success": True,
                "cluster": serialize_cluster(cluster, user=request.user),
                "workloads": _workload_rows(cluster, user=request.user),
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_cluster_events(request, cluster_id: str):
    def handler():
        cluster = _cluster_or_none(cluster_id)
        if cluster is None:
            return JsonResponse({"success": False, "error": "Cluster not found"}, status=404)
        return JsonResponse(
            {
                "success": True,
                "cluster": serialize_cluster(cluster, user=request.user),
                "events": _cluster_event_rows(cluster),
            }
        )

    return _safe_json(handler)


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_fleet_bundles(request):
    return _safe_json(
        lambda: JsonResponse(
            {
                "success": True,
                "bundles": [
                    serialize_fleet_bundle(bundle, user=request.user) for bundle in K8sFleetBundle.objects.all()
                ],
            }
        )
    )


@login_required
@require_feature("kubernetes")
@require_GET
def api_kubernetes_devtron_apps(request):
    apps = K8sAppRef.objects.filter(owner=K8sAppRef.OWNER_DEVTRON).select_related("cluster")
    return _safe_json(
        lambda: JsonResponse({"success": True, "apps": [serialize_app(app, user=request.user) for app in apps]})
    )
