from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods

from core_ui.decorators import require_feature
from core_ui.managed_secrets import delete_kubernetes_provider_token
from kubernetes_ops.models import (
    K8sAppRef,
    K8sCluster,
    K8sFleetBundle,
    K8sProvider,
)
from kubernetes_ops.serializers import (
    serialize_app,
    serialize_cluster,
    serialize_fleet_bundle,
    serialize_provider,
)
from kubernetes_ops.services.overview import build_overview_payload
from kubernetes_ops.services.readiness import build_kubernetes_readiness_report
from kubernetes_ops.services.sync import sync_kubernetes_providers
from kubernetes_ops.views_helpers import (
    _apply_provider_secret_value,
    _as_bool,
    _audit,
    _cluster_event_rows,
    _cluster_or_none,
    _delete_managed_provider_secret_if_external,
    _json_body,
    _namespace_summaries,
    _provider_payload_from_body,
    _safe_json,
    _staff_required,
    _sync_result_payload,
    _workload_rows,
)


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
