from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sFleetBundle, K8sWorkloadRef
from kubernetes_ops.services.action_sanitizers import bounded_action_text, sanitize_action_value, sanitize_public_links
from kubernetes_ops.services.admin_resources import cluster_for_value

SCHEMA_VERSION = "kubernetes_ops.helm_ownership.v1"
MAX_RELEASES = 150
MAX_RELATED = 25
HELM_RELEASE_KEYS = (
    "meta.helm.sh/release-name",
    "helm.sh/release",
    "helm.toolkit.fluxcd.io/name",
    "app.kubernetes.io/instance",
    "release",
)
FLEET_LABEL_PREFIXES = ("fleet.cattle.io/", "objectset.rio.cattle.io/")


@dataclass
class ReleaseBucket:
    release_name: str
    namespace: str
    cluster: K8sCluster | None = None
    owners: set[str] = field(default_factory=set)
    owner_evidence: set[str] = field(default_factory=set)
    workloads: list[K8sWorkloadRef] = field(default_factory=list)
    apps: list[K8sAppRef] = field(default_factory=list)
    fleet_bundles: list[K8sFleetBundle] = field(default_factory=list)


def build_helm_ownership_payload(
    *,
    user=None,
    cluster_id: str = "",
    namespace: str = "",
    owner: str = "",
    limit: int | str | None = None,
) -> dict[str, Any]:
    cluster = cluster_for_value(cluster_id) if cluster_id else None
    if cluster_id and cluster is None:
        return {
            "success": False,
            "code": "cluster_not_found",
            "error": "Cluster not found.",
            "schema_version": SCHEMA_VERSION,
        }
    max_items = _bounded_limit(limit)
    buckets: dict[str, ReleaseBucket] = {}
    _add_workloads(buckets, cluster=cluster, namespace=namespace)
    _add_apps(buckets, cluster=cluster, namespace=namespace)
    _add_fleet_bundles(buckets, cluster=cluster, namespace=namespace)
    rows = [_bucket_payload(bucket, user=user) for bucket in buckets.values()]
    if owner:
        rows = [row for row in rows if owner in set(row.get("owners") or []) or row.get("primary_owner") == owner]
    rows = sorted(
        rows,
        key=lambda item: (item.get("cluster_name") or "", item.get("namespace") or "", item.get("release_name") or ""),
    )[:max_items]
    summary = _summary(rows)
    return {
        "success": True,
        "schema_version": SCHEMA_VERSION,
        "mode": "read_only",
        "source": "normalized_inventory",
        "filters": {
            "cluster_id": f"cluster_{cluster.id}" if cluster else "",
            "namespace": bounded_action_text(namespace, limit=120),
            "owner": bounded_action_text(owner, limit=40),
            "limit": max_items,
        },
        "summary": summary,
        "policy": {
            "mode": "read_only",
            "mutates_state": False,
            "one_release_one_owner_required": True,
            "conflict_change_path": "resolve_owner_before_mutation",
            "external_ui": "staff_admin_fallback",
        },
        "items": rows,
    }


def helm_ownership_audit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    return {
        "release_count": int(summary.get("release_count") or 0),
        "conflict_count": int(summary.get("conflict_count") or 0),
        "guarded_count": int(summary.get("guarded_count") or 0),
        "owners": sanitize_action_value(summary.get("owners") or {}),
        "filters": sanitize_action_value(filters),
    }


def _add_workloads(buckets: dict[str, ReleaseBucket], *, cluster: K8sCluster | None, namespace: str) -> None:
    queryset = K8sWorkloadRef.objects.select_related("cluster").order_by("cluster__name", "namespace", "kind", "name")[
        :600
    ]
    for workload in queryset:
        if cluster and workload.cluster_id != cluster.id:
            continue
        if namespace and workload.namespace != namespace:
            continue
        release = _release_name(workload.labels, fallback=workload.name)
        if not release or not _release_like(workload.labels, owner=workload.owner):
            continue
        bucket = _bucket(buckets, cluster=workload.cluster, namespace=workload.namespace, release=release)
        bucket.workloads.append(workload)
        owner = _owner_from_workload(workload)
        bucket.owners.add(owner)
        bucket.owner_evidence.add(f"workload:{owner}")


def _add_apps(buckets: dict[str, ReleaseBucket], *, cluster: K8sCluster | None, namespace: str) -> None:
    queryset = K8sAppRef.objects.select_related("cluster").order_by("cluster__name", "namespace", "name")[:400]
    for app in queryset:
        if cluster and app.cluster_id != cluster.id:
            continue
        if namespace and app.namespace != namespace:
            continue
        release = _release_name(app.labels, fallback=app.name)
        bucket = _bucket(buckets, cluster=app.cluster, namespace=app.namespace, release=release)
        bucket.apps.append(app)
        bucket.owners.add(app.owner or "unknown")
        bucket.owner_evidence.add(f"app:{app.owner or 'unknown'}")


def _add_fleet_bundles(buckets: dict[str, ReleaseBucket], *, cluster: K8sCluster | None, namespace: str) -> None:
    if cluster and not buckets:
        return
    for bundle in K8sFleetBundle.objects.order_by("name")[:300]:
        candidates = _bundle_candidates(bundle)
        if not candidates:
            continue
        target_namespace = _target_namespace(bundle)
        if namespace and target_namespace and namespace != target_namespace:
            continue
        key = _existing_bundle_key(
            buckets, candidates=candidates, namespace=namespace or target_namespace, cluster=cluster
        )
        if key:
            bucket = buckets[key]
        elif cluster:
            continue
        else:
            bucket = _bucket(buckets, cluster=None, namespace=target_namespace, release=sorted(candidates)[0])
        bucket.fleet_bundles.append(bundle)
        bucket.owners.add(K8sAppRef.OWNER_FLEET)
        bucket.owner_evidence.add("fleet_bundle:fleet")


def _bucket(
    buckets: dict[str, ReleaseBucket], *, cluster: K8sCluster | None, namespace: str, release: str
) -> ReleaseBucket:
    safe_release = bounded_action_text(release, limit=180)
    safe_namespace = bounded_action_text(namespace, limit=120)
    key = _bucket_key(cluster=cluster, namespace=safe_namespace, release=safe_release)
    if key not in buckets:
        buckets[key] = ReleaseBucket(release_name=safe_release, namespace=safe_namespace, cluster=cluster)
    return buckets[key]


def _bucket_key(*, cluster: K8sCluster | None, namespace: str, release: str) -> str:
    cluster_part = str(cluster.id) if cluster else "fleet"
    return f"{cluster_part}:{namespace}:{release}".lower()


def _existing_bundle_key(
    buckets: dict[str, ReleaseBucket],
    *,
    candidates: set[str],
    namespace: str,
    cluster: K8sCluster | None,
) -> str:
    for key, bucket in buckets.items():
        if cluster and bucket.cluster and bucket.cluster.id != cluster.id:
            continue
        if namespace and bucket.namespace and bucket.namespace != namespace:
            continue
        if bucket.release_name in candidates or _short_name(bucket.release_name) in candidates:
            return key
    return ""


def _bucket_payload(bucket: ReleaseBucket, *, user=None) -> dict[str, Any]:
    owners = sorted(bucket.owners or {"unknown"})
    known_owners = [owner for owner in owners if owner != "unknown"]
    conflict = len(set(known_owners)) > 1
    primary_owner = "" if conflict else (known_owners[0] if known_owners else "unknown")
    policy = _policy(primary_owner=primary_owner, conflict=conflict)
    cluster = bucket.cluster
    return {
        "release_key": _bucket_key(cluster=cluster, namespace=bucket.namespace, release=bucket.release_name),
        "release_name": bucket.release_name,
        "namespace": bucket.namespace,
        "cluster_id": f"cluster_{cluster.id}" if cluster else "",
        "cluster_database_id": cluster.id if cluster else None,
        "cluster_name": cluster.name if cluster else "",
        "owners": owners,
        "owner_count": len(owners),
        "primary_owner": primary_owner,
        "conflict": conflict,
        "one_release_one_owner": len(owners) == 1 and owners[0] != "unknown",
        "status": _status(bucket),
        "policy": policy,
        "evidence": sorted(bucket.owner_evidence),
        "counts": {
            "workloads": len(bucket.workloads),
            "apps": len(bucket.apps),
            "fleet_bundles": len(bucket.fleet_bundles),
        },
        "workloads": [_workload_payload(item, user=user) for item in bucket.workloads[:MAX_RELATED]],
        "apps": [_app_payload(item, user=user) for item in bucket.apps[:MAX_RELATED]],
        "fleet_bundles": [_bundle_payload(item, user=user) for item in bucket.fleet_bundles[:MAX_RELATED]],
    }


def _policy(*, primary_owner: str, conflict: bool) -> dict[str, Any]:
    if conflict:
        change_path = "resolve_owner_before_mutation"
    elif primary_owner == K8sAppRef.OWNER_FLEET:
        change_path = "fleet_gitops_or_mr"
    elif primary_owner == K8sAppRef.OWNER_DEVTRON:
        change_path = "devtron_rollback_or_deploy"
    elif primary_owner == K8sAppRef.OWNER_EXTERNAL:
        change_path = "external_owner_flow"
    elif primary_owner in {"rancher", "webterm"}:
        change_path = "webterm_admin_session"
    else:
        change_path = "ownership_review_required"
    guarded = conflict or primary_owner in {
        K8sAppRef.OWNER_FLEET,
        K8sAppRef.OWNER_DEVTRON,
        K8sAppRef.OWNER_EXTERNAL,
        "unknown",
    }
    return {
        "change_path": change_path,
        "direct_mutation_policy": "blocked_by_default" if guarded else "webterm_admin_session_required",
        "write_requires_approval": True,
        "blocked_actions": ["helm_delete", "direct_apply", "direct_patch", "direct_restart", "direct_scale"]
        if guarded
        else [],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    owner_counts = Counter()
    for row in rows:
        for owner in row.get("owners") or ["unknown"]:
            owner_counts[str(owner)] += 1
    return {
        "release_count": len(rows),
        "conflict_count": sum(1 for row in rows if row.get("conflict")),
        "guarded_count": sum(
            1 for row in rows if row.get("policy", {}).get("direct_mutation_policy") == "blocked_by_default"
        ),
        "one_owner_count": sum(1 for row in rows if row.get("one_release_one_owner")),
        "owners": dict(sorted(owner_counts.items())),
    }


def _release_name(labels: Any, *, fallback: str) -> str:
    labels = labels if isinstance(labels, dict) else {}
    for key in HELM_RELEASE_KEYS:
        value = str(labels.get(key) or "").strip()
        if value:
            return bounded_action_text(value, limit=180)
    return bounded_action_text(fallback, limit=180)


def _release_like(labels: Any, *, owner: str = "") -> bool:
    labels = labels if isinstance(labels, dict) else {}
    if any(str(labels.get(key) or "").strip() for key in HELM_RELEASE_KEYS):
        return True
    managed_by = str(labels.get("app.kubernetes.io/managed-by") or labels.get("managed-by") or "").lower()
    if managed_by in {"helm", "fleet", "devtron"}:
        return True
    if any(str(key).startswith(FLEET_LABEL_PREFIXES) for key in labels):
        return True
    return any(marker in str(owner or "").lower() for marker in ("helm", "fleet", "devtron", "external"))


def _owner_from_workload(workload: K8sWorkloadRef) -> str:
    labels = workload.labels if isinstance(workload.labels, dict) else {}
    managed_by = str(labels.get("app.kubernetes.io/managed-by") or labels.get("managed-by") or "").lower()
    owner_text = str(workload.owner or "").lower()
    if "devtron" in managed_by or "devtron" in owner_text:
        return K8sAppRef.OWNER_DEVTRON
    if (
        "fleet" in managed_by
        or "fleet" in owner_text
        or any(str(key).startswith(FLEET_LABEL_PREFIXES) for key in labels)
    ):
        return K8sAppRef.OWNER_FLEET
    if "external" in owner_text:
        return K8sAppRef.OWNER_EXTERNAL
    if "webterm" in owner_text:
        return "webterm"
    return "rancher"


def _bundle_candidates(bundle: K8sFleetBundle) -> set[str]:
    values = {_short_name(bundle.name), bundle.name}
    labels = bundle.labels if isinstance(bundle.labels, dict) else {}
    for key in HELM_RELEASE_KEYS:
        values.add(str(labels.get(key) or ""))
    return {bounded_action_text(value, limit=180) for value in values if str(value or "").strip()}


def _target_namespace(bundle: K8sFleetBundle) -> str:
    target = str(bundle.target or "").strip()
    if target and not any(char in target for char in "*[],{}"):
        return bounded_action_text(target, limit=120)
    labels = bundle.labels if isinstance(bundle.labels, dict) else {}
    return bounded_action_text(labels.get("namespace") or labels.get("targetNamespace") or "", limit=120)


def _short_name(value: str) -> str:
    text = str(value or "").strip()
    return text.rsplit("/", 1)[-1] if "/" in text else text


def _status(bucket: ReleaseBucket) -> str:
    states = [item.health for item in [*bucket.workloads, *bucket.apps] if item.health]
    states.extend(item.status for item in bucket.fleet_bundles if item.status)
    if any(state in {K8sCluster.HEALTH_DEGRADED, K8sFleetBundle.STATUS_DEGRADED} for state in states):
        return "degraded"
    if any(
        state in {K8sCluster.HEALTH_WARNING, K8sFleetBundle.STATUS_ROLLING, K8sFleetBundle.STATUS_PAUSED}
        for state in states
    ):
        return "warning"
    if states and all(state in {K8sCluster.HEALTH_HEALTHY, K8sFleetBundle.STATUS_READY} for state in states):
        return "healthy"
    return "unknown"


def _workload_payload(workload: K8sWorkloadRef, *, user=None) -> dict[str, Any]:
    return {
        "id": f"workload_{workload.id}",
        "name": workload.name,
        "namespace": workload.namespace,
        "kind": workload.kind,
        "owner": workload.owner,
        "team": workload.team,
        "health": workload.health,
        "ready": workload.ready,
        "desired": workload.desired,
        "version": workload.version,
        "labels": sanitize_action_value(workload.labels or {}),
        "links": _links(workload.links, user=user),
    }


def _app_payload(app: K8sAppRef, *, user=None) -> dict[str, Any]:
    return {
        "id": f"app_{app.id}",
        "name": app.name,
        "namespace": app.namespace,
        "owner": app.owner,
        "team": app.team,
        "health": app.health,
        "version": app.version,
        "labels": sanitize_action_value(app.labels or {}),
        "links": _links(app.links, user=user),
    }


def _bundle_payload(bundle: K8sFleetBundle, *, user=None) -> dict[str, Any]:
    return {
        "id": f"fleet_{bundle.id}",
        "name": bundle.name,
        "source": bounded_action_text(bundle.source, limit=240),
        "target": bounded_action_text(bundle.target, limit=240),
        "status": bundle.status,
        "ready": bundle.ready,
        "desired": bundle.desired,
        "labels": sanitize_action_value(bundle.labels or {}),
        "links": _links(bundle.links, user=user),
    }


def _links(value: Any, *, user=None) -> Any:
    if not getattr(user, "is_staff", False):
        return {}
    return sanitize_public_links(value or {})


def _bounded_limit(value: int | str | None) -> int:
    try:
        return max(1, min(int(value or 100), MAX_RELEASES))
    except (TypeError, ValueError):
        return 100
