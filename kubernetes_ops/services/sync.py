from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from kubernetes_ops.models import (
    K8sAppRef,
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.services.normalizers import (
    normalize_devtron_app,
    normalize_fleet_bundle,
    normalize_rancher_cluster,
    normalize_rancher_event,
    normalize_rancher_ingress,
    normalize_rancher_namespace,
    normalize_rancher_pod,
    normalize_rancher_service,
    normalize_rancher_workload,
    payload_items,
)
from kubernetes_ops.services.provider_clients import DevtronClient, ProviderTransport, RancherClient
from kubernetes_ops.services.secrets import redact_secret, resolve_provider_token


@dataclass
class KubernetesSyncResult:
    provider_id: int
    provider_name: str
    provider_kind: str
    success: bool
    clusters: int = 0
    namespaces: int = 0
    workloads: int = 0
    pods: int = 0
    services: int = 0
    ingresses: int = 0
    events: int = 0
    apps: int = 0
    fleet_bundles: int = 0
    error: str = ""
    dry_run: bool = False


def _provider_queryset(*, provider_id: int | None = None, kind: str = ""):
    queryset = K8sProvider.objects.filter(enabled=True).order_by("kind", "name")
    if provider_id is not None:
        queryset = queryset.filter(id=provider_id)
    if kind:
        queryset = queryset.filter(kind=kind)
    return queryset


def sync_kubernetes_providers(
    *,
    provider_id: int | None = None,
    kind: str = "",
    dry_run: bool = False,
    transport: ProviderTransport | None = None,
) -> list[KubernetesSyncResult]:
    results: list[KubernetesSyncResult] = []
    for provider in _provider_queryset(provider_id=provider_id, kind=kind):
        if provider.kind == K8sProvider.KIND_RANCHER:
            results.append(sync_rancher_provider(provider, dry_run=dry_run, transport=transport))
        elif provider.kind == K8sProvider.KIND_DEVTRON:
            results.append(sync_devtron_provider(provider, dry_run=dry_run, transport=transport))
    return results


def sync_rancher_provider(
    provider: K8sProvider,
    *,
    dry_run: bool = False,
    transport: ProviderTransport | None = None,
) -> KubernetesSyncResult:
    token = ""
    try:
        token = resolve_provider_token(provider)
        client = RancherClient(provider, transport=transport)
        clusters = [normalize_rancher_cluster(provider, item) for item in payload_items(client.list_clusters())]
        namespaces = [
            normalize_rancher_namespace(item)
            for item in _with_default_cluster_context(payload_items(client.list_namespaces()), clusters)
        ]
        workloads = [
            normalize_rancher_workload(item)
            for item in _with_default_cluster_context(payload_items(client.list_workloads()), clusters)
        ]
        pods = [
            normalize_rancher_pod(item)
            for item in _with_default_cluster_context(payload_items(client.list_pods()), clusters)
        ]
        services = [
            normalize_rancher_service(item)
            for item in _with_default_cluster_context(payload_items(client.list_services()), clusters)
        ]
        ingresses = [
            normalize_rancher_ingress(item)
            for item in _with_default_cluster_context(payload_items(client.list_ingresses()), clusters)
        ]
        events = [
            normalize_rancher_event(item)
            for item in _with_default_cluster_context(payload_items(client.list_events()), clusters)
        ]
        bundles = [normalize_fleet_bundle(provider, item) for item in payload_items(client.list_fleet_bundles())]
        if not dry_run:
            _upsert_rancher_rows(provider, clusters, namespaces, workloads, pods, services + ingresses, events, bundles)
        _mark_provider_success(provider, dry_run=dry_run)
        return KubernetesSyncResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            clusters=len(clusters),
            namespaces=len(namespaces),
            workloads=len(workloads),
            pods=len(pods),
            services=len(services),
            ingresses=len(ingresses),
            events=len(events),
            fleet_bundles=len(bundles),
            dry_run=dry_run,
        )
    except Exception as exc:
        error = redact_secret(exc, token)
        _mark_provider_error(provider, error, dry_run=dry_run)
        return KubernetesSyncResult(provider.id, provider.name, provider.kind, False, error=error, dry_run=dry_run)


def _with_default_cluster_context(items: list[dict], clusters: list[dict]) -> list[dict]:
    if not items or not clusters:
        return items
    default = clusters[0]
    cluster_id = str(default.get("rancher_cluster_id") or "")
    cluster_name = str(default.get("name") or cluster_id)
    if not cluster_id and not cluster_name:
        return items
    enriched = []
    for item in items:
        if item.get("clusterId") or item.get("cluster_id"):
            enriched.append(item)
            continue
        copy = dict(item)
        copy["clusterId"] = cluster_id
        copy["clusterName"] = cluster_name
        enriched.append(copy)
    return enriched


def _with_devtron_cluster_alias(provider: K8sProvider, row: dict) -> dict:
    labels = provider.labels if isinstance(provider.labels, dict) else {}
    aliases = labels.get("cluster_name_map") or labels.get("cluster_aliases") or {}
    id_aliases = labels.get("devtron_cluster_id_map") or {}
    if not isinstance(aliases, dict) and not isinstance(id_aliases, dict):
        return row
    cluster_name = str(row.get("cluster_name") or "")
    devtron_cluster_id = str(row.get("devtron_cluster_id") or "")
    mapped_name = ""
    if isinstance(id_aliases, dict):
        mapped_name = str(id_aliases.get(devtron_cluster_id) or "")
    if not mapped_name and isinstance(aliases, dict):
        mapped_name = str(aliases.get(cluster_name) or "")
    if not mapped_name:
        return row
    copy = dict(row)
    copy["cluster_name"] = mapped_name
    return copy


def sync_devtron_provider(
    provider: K8sProvider,
    *,
    dry_run: bool = False,
    transport: ProviderTransport | None = None,
) -> KubernetesSyncResult:
    token = ""
    try:
        token = resolve_provider_token(provider)
        client = DevtronClient(provider, transport=transport)
        apps = [normalize_devtron_app(item) for item in payload_items(client.list_apps())]
        apps = [item for item in apps if item["name"]]
        apps = [_with_devtron_cluster_alias(provider, item) for item in apps]
        if not dry_run:
            _upsert_devtron_rows(apps)
        _mark_provider_success(provider, dry_run=dry_run)
        cluster_count = len({item["cluster_name"] for item in apps})
        return KubernetesSyncResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            clusters=cluster_count,
            apps=len(apps),
            dry_run=dry_run,
        )
    except Exception as exc:
        error = redact_secret(exc, token)
        _mark_provider_error(provider, error, dry_run=dry_run)
        return KubernetesSyncResult(provider.id, provider.name, provider.kind, False, error=error, dry_run=dry_run)


def _cluster_for_rancher_row(row: dict, provider: K8sProvider) -> K8sCluster:
    rancher_cluster_id = row.get("cluster_rancher_id") or row.get("rancher_cluster_id") or ""
    cluster_name = row.get("cluster_name") or row.get("name") or rancher_cluster_id or "rancher"
    cluster = K8sCluster.objects.filter(rancher_cluster_id=rancher_cluster_id).first() if rancher_cluster_id else None
    cluster = cluster or K8sCluster.objects.filter(name=cluster_name).first()
    if cluster is None:
        cluster = K8sCluster.objects.create(
            name=cluster_name,
            rancher_provider=provider,
            rancher_cluster_id=rancher_cluster_id,
            health=K8sCluster.HEALTH_UNKNOWN,
            last_sync_at=timezone.now(),
        )
    return cluster


def _event_time(value):
    if value is None:
        return None
    return timezone.make_aware(value, timezone.get_current_timezone()) if timezone.is_naive(value) else value


@transaction.atomic
def _upsert_rancher_rows(
    provider: K8sProvider,
    clusters: list[dict],
    namespaces: list[dict],
    workloads: list[dict],
    pods: list[dict],
    network_refs: list[dict],
    events: list[dict],
    bundles: list[dict],
) -> None:
    now = timezone.now()
    for row in clusters:
        cluster = None
        if row["rancher_cluster_id"]:
            cluster = K8sCluster.objects.filter(rancher_cluster_id=row["rancher_cluster_id"]).first()
        cluster = cluster or K8sCluster.objects.filter(name=row["name"]).first() or K8sCluster(name=row["name"])
        cluster.name = row["name"]
        cluster.environment = row["environment"]
        cluster.health = row["health"]
        cluster.rancher_provider = provider
        cluster.rancher_cluster_id = row["rancher_cluster_id"]
        cluster.nodes_ready = row["nodes_ready"]
        cluster.nodes_total = row["nodes_total"]
        cluster.namespace_count = row["namespace_count"]
        cluster.workload_count = row["workload_count"]
        cluster.labels = row["labels"]
        cluster.links = {**(cluster.links or {}), **row["links"]}
        cluster.last_sync_at = now
        cluster.save()
    for row in namespaces:
        if not row["name"]:
            continue
        cluster = _cluster_for_rancher_row(row, provider)
        K8sNamespace.objects.update_or_create(
            cluster=cluster,
            name=row["name"],
            defaults={
                "environment": row["environment"] or cluster.environment,
                "health": row["health"],
                "app_count": row["app_count"],
                "workload_count": row["workload_count"],
                "labels": row["labels"],
                "links": row["links"],
                "last_sync_at": now,
            },
        )
    for row in workloads:
        if not row["name"]:
            continue
        cluster = _cluster_for_rancher_row(row, provider)
        K8sWorkloadRef.objects.update_or_create(
            cluster=cluster,
            namespace=row["namespace"],
            kind=row["kind"],
            name=row["name"],
            defaults={
                "environment": row["environment"] or cluster.environment,
                "owner": row["owner"],
                "team": row["team"],
                "health": row["health"],
                "ready": row["ready"],
                "desired": row["desired"],
                "version": row["version"],
                "links": row["links"],
                "labels": row["labels"],
                "last_sync_at": now,
            },
        )
    for row in pods:
        if not row["name"]:
            continue
        cluster = _cluster_for_rancher_row(row, provider)
        K8sPodRef.objects.update_or_create(
            cluster=cluster,
            namespace=row["namespace"],
            name=row["name"],
            defaults={
                "environment": row["environment"] or cluster.environment,
                "health": row["health"],
                "phase": row["phase"],
                "node_name": row["node_name"],
                "pod_ip": row["pod_ip"],
                "host_ip": row["host_ip"],
                "owner_kind": row["owner_kind"],
                "owner_name": row["owner_name"],
                "ready_containers": row["ready_containers"],
                "total_containers": row["total_containers"],
                "restart_count": row["restart_count"],
                "images": row["images"],
                "links": row["links"],
                "labels": row["labels"],
                "last_sync_at": now,
            },
        )
    for row in network_refs:
        if not row["name"]:
            continue
        cluster = _cluster_for_rancher_row(row, provider)
        K8sNetworkRef.objects.update_or_create(
            cluster=cluster,
            namespace=row["namespace"],
            kind=row["kind"],
            name=row["name"],
            defaults={
                "environment": row["environment"] or cluster.environment,
                "health": row["health"],
                "service_type": row["service_type"],
                "ports": row["ports"],
                "hosts": row["hosts"],
                "endpoints": row["endpoints"],
                "links": row["links"],
                "labels": row["labels"],
                "last_sync_at": now,
            },
        )
    for row in events:
        if not row["event_uid"]:
            continue
        cluster = _cluster_for_rancher_row(row, provider)
        K8sEvent.objects.update_or_create(
            cluster=cluster,
            event_uid=row["event_uid"],
            defaults={
                "source": row["source"],
                "severity": row["severity"],
                "reason": row["reason"],
                "message": row["message"],
                "namespace": row["namespace"],
                "involved_kind": row["involved_kind"],
                "involved_name": row["involved_name"],
                "count": row["count"],
                "first_seen_at": _event_time(row["first_seen_at"]),
                "last_seen_at": _event_time(row["last_seen_at"]) or now,
                "labels": row["labels"],
                "last_sync_at": now,
            },
        )
    for row in bundles:
        if not row["name"]:
            continue
        K8sFleetBundle.objects.update_or_create(name=row["name"], defaults={**row, "last_sync_at": now})
    _prune_stale_rancher_rows(provider, now)
    _refresh_cluster_inventory_counts(provider)


def _prune_stale_rancher_rows(provider: K8sProvider, synced_at) -> None:
    provider_clusters = K8sCluster.objects.filter(rancher_provider=provider)
    K8sNamespace.objects.filter(cluster__in=provider_clusters).exclude(last_sync_at=synced_at).delete()
    K8sWorkloadRef.objects.filter(cluster__in=provider_clusters).exclude(last_sync_at=synced_at).delete()
    K8sPodRef.objects.filter(cluster__in=provider_clusters).exclude(last_sync_at=synced_at).delete()
    K8sNetworkRef.objects.filter(cluster__in=provider_clusters).exclude(last_sync_at=synced_at).delete()
    K8sEvent.objects.filter(cluster__in=provider_clusters).exclude(last_sync_at=synced_at).delete()


def _refresh_cluster_inventory_counts(provider: K8sProvider) -> None:
    namespace_counts = dict(
        K8sNamespace.objects.filter(cluster__rancher_provider=provider)
        .values("cluster_id")
        .annotate(total=Count("id"))
        .values_list("cluster_id", "total")
    )
    workload_counts = dict(
        K8sWorkloadRef.objects.filter(cluster__rancher_provider=provider)
        .values("cluster_id")
        .annotate(total=Count("id"))
        .values_list("cluster_id", "total")
    )
    for cluster in K8sCluster.objects.filter(rancher_provider=provider):
        update_fields = []
        namespace_count = namespace_counts.get(cluster.id)
        workload_count = workload_counts.get(cluster.id)
        if namespace_count is not None and cluster.namespace_count != namespace_count:
            cluster.namespace_count = namespace_count
            update_fields.append("namespace_count")
        if workload_count is not None and cluster.workload_count != workload_count:
            cluster.workload_count = workload_count
            update_fields.append("workload_count")
        if update_fields:
            cluster.save(update_fields=update_fields)


@transaction.atomic
def _upsert_devtron_rows(apps: list[dict]) -> None:
    now = timezone.now()
    touched_cluster_ids: set[int] = set()
    for row in apps:
        cluster = None
        if row["devtron_cluster_id"]:
            cluster = K8sCluster.objects.filter(devtron_cluster_id=row["devtron_cluster_id"]).first()
        cluster = (
            cluster
            or K8sCluster.objects.filter(name=row["cluster_name"]).first()
            or K8sCluster(name=row["cluster_name"])
        )
        cluster.devtron_cluster_id = row["devtron_cluster_id"] or cluster.devtron_cluster_id
        cluster.environment = cluster.environment or row["environment"]
        cluster.health = cluster.health or K8sCluster.HEALTH_UNKNOWN
        cluster.last_sync_at = now
        cluster.save()
        touched_cluster_ids.add(cluster.id)
        K8sAppRef.objects.update_or_create(
            cluster=cluster,
            namespace=row["namespace"],
            name=row["name"],
            defaults={
                "environment": row["environment"],
                "owner": K8sAppRef.OWNER_DEVTRON,
                "team": row["team"],
                "health": row["health"],
                "version": row["version"],
                "links": row["links"],
                "labels": row["labels"],
                "last_sync_at": now,
            },
        )
    if touched_cluster_ids:
        K8sAppRef.objects.filter(owner=K8sAppRef.OWNER_DEVTRON, cluster_id__in=touched_cluster_ids).exclude(
            last_sync_at=now
        ).delete()


def _mark_provider_success(provider: K8sProvider, *, dry_run: bool) -> None:
    if dry_run:
        return
    provider.last_sync_at = timezone.now()
    provider.last_error = ""
    provider.save(update_fields=["last_sync_at", "last_error"])


def _mark_provider_error(provider: K8sProvider, error: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    provider.last_error = error
    provider.save(update_fields=["last_error"])
