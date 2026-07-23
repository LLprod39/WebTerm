from __future__ import annotations

from collections import Counter
from typing import Any

from django.db.models import Q

from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sFleetBundle, K8sWorkloadRef
from kubernetes_ops.services.describe import sanitize_links, sanitize_metadata


def build_admin_resource_ownership(
    *, cluster: K8sCluster, ref, resource: dict[str, Any] | None = None
) -> dict[str, Any]:
    metadata = resource.get("metadata") if isinstance(resource, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), dict) else {}
    namespace = str(ref.namespace or metadata.get("namespace") or "").strip()
    name = str(ref.name or metadata.get("name") or "").strip()
    kind = str((resource or {}).get("kind") or ref.kind or "").strip()

    workload = _match_workload(cluster=cluster, namespace=namespace, name=name, kind=kind, labels=labels)
    app = _match_app(cluster=cluster, namespace=namespace, name=name, labels=labels)
    bundle = _match_fleet_bundle(labels=labels, annotations=annotations)
    label_owner = _label_owner(labels, annotations)
    owner = _select_owner(workload=workload, app=app, bundle=bundle, label_owner=label_owner)
    confidence = _confidence(owner=owner, workload=workload, app=app, bundle=bundle, label_owner=label_owner)

    return {
        "owner": owner,
        "confidence": confidence,
        "change_path": _change_path(owner),
        "direct_apply_policy": _direct_apply_policy(owner),
        "current_mode": "read_only",
        "warnings": _warnings(owner),
        "evidence": _evidence(workload=workload, app=app, bundle=bundle, label_owner=label_owner),
        "workload": _workload_payload(workload),
        "app": _app_payload(app),
        "fleet_bundle": _bundle_payload(bundle),
    }


def attach_item_ownership(*, cluster: K8sCluster, ref, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["webterm_ownership"] = build_admin_resource_ownership(cluster=cluster, ref=ref, resource=item)
        output.append(row)
    return output


def summarize_ownership(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("owner") or "unknown") for item in contexts)
    guarded = sum(1 for item in contexts if item.get("direct_apply_policy") == "blocked_by_default")
    return {
        "owners": dict(sorted(counts.items())),
        "guarded_items": guarded,
        "total": len(contexts),
    }


def _match_workload(
    *, cluster: K8sCluster, namespace: str, name: str, kind: str, labels: dict[str, Any]
) -> K8sWorkloadRef | None:
    if not namespace:
        return None
    kind_value = _workload_kind(kind)
    names = _candidate_names(name, labels)
    query = Q()
    if kind_value:
        query &= Q(kind=kind_value)
    name_query = Q()
    for candidate in names:
        name_query |= Q(name=candidate)
    if not name_query:
        return None
    return K8sWorkloadRef.objects.filter(cluster=cluster, namespace=namespace).filter(query & name_query).first()


def _match_app(*, cluster: K8sCluster, namespace: str, name: str, labels: dict[str, Any]) -> K8sAppRef | None:
    if not namespace:
        return None
    name_query = Q()
    for candidate in _candidate_names(name, labels):
        name_query |= Q(name=candidate)
    if not name_query:
        return None
    return K8sAppRef.objects.filter(cluster=cluster, namespace=namespace).filter(name_query).first()


def _match_fleet_bundle(*, labels: dict[str, Any], annotations: dict[str, Any]) -> K8sFleetBundle | None:
    candidates: set[str] = set()
    for values in (labels, annotations):
        for key, value in values.items():
            text_key = str(key)
            if text_key.startswith("fleet.cattle.io/") or text_key.startswith("objectset.rio.cattle.io/"):
                text_value = str(value or "").strip()
                if text_value:
                    candidates.add(text_value)
                    if "/" in text_value:
                        candidates.add(text_value.rsplit("/", 1)[-1])
    if not candidates:
        return None
    query = Q()
    for candidate in candidates:
        query |= Q(name=candidate) | Q(name__iendswith=f"/{candidate}")
    return K8sFleetBundle.objects.filter(query).first()


def _candidate_names(name: str, labels: dict[str, Any]) -> list[str]:
    candidates = [
        name,
        labels.get("app.kubernetes.io/name"),
        labels.get("app.kubernetes.io/instance"),
        labels.get("app"),
        labels.get("appName"),
        labels.get("devtron.ai/app-name"),
    ]
    seen: set[str] = set()
    output: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _label_owner(labels: dict[str, Any], annotations: dict[str, Any]) -> str:
    values = {**annotations, **labels}
    managed_by = str(
        values.get("app.kubernetes.io/managed-by") or values.get("managed-by") or values.get("owner") or ""
    ).lower()
    if "devtron" in managed_by:
        return K8sAppRef.OWNER_DEVTRON
    if "fleet" in managed_by:
        return K8sAppRef.OWNER_FLEET
    if any(str(key).startswith(("fleet.cattle.io/", "objectset.rio.cattle.io/")) for key in values):
        return K8sAppRef.OWNER_FLEET
    return ""


def _select_owner(
    *, workload: K8sWorkloadRef | None, app: K8sAppRef | None, bundle: K8sFleetBundle | None, label_owner: str
) -> str:
    if app and app.owner:
        return app.owner
    if bundle:
        return K8sAppRef.OWNER_FLEET
    if label_owner:
        return label_owner
    workload_owner = str(workload.owner if workload else "").lower()
    if "devtron" in workload_owner:
        return K8sAppRef.OWNER_DEVTRON
    if "fleet" in workload_owner:
        return K8sAppRef.OWNER_FLEET
    return "rancher" if workload else "unknown"


def _confidence(
    *,
    owner: str,
    workload: K8sWorkloadRef | None,
    app: K8sAppRef | None,
    bundle: K8sFleetBundle | None,
    label_owner: str,
) -> str:
    if app or bundle or workload:
        return "normalized_inventory"
    if label_owner:
        return "metadata_label"
    return "none" if owner == "unknown" else "default"


def _change_path(owner: str) -> str:
    if owner == K8sAppRef.OWNER_DEVTRON:
        return "devtron_app_flow"
    if owner == K8sAppRef.OWNER_FLEET:
        return "fleet_gitops_or_mr"
    if owner == K8sAppRef.OWNER_EXTERNAL:
        return "external_owner_flow"
    return "webterm_admin_session"


def _direct_apply_policy(owner: str) -> str:
    if owner in {K8sAppRef.OWNER_DEVTRON, K8sAppRef.OWNER_FLEET, K8sAppRef.OWNER_EXTERNAL}:
        return "blocked_by_default"
    return "disabled_in_current_build"


def _warnings(owner: str) -> list[str]:
    if owner == K8sAppRef.OWNER_DEVTRON:
        return ["Devtron-owned resource: prefer Devtron AppOps flow or audited rollback context."]
    if owner == K8sAppRef.OWNER_FLEET:
        return ["Fleet/GitOps-owned resource: prefer GitOps MR/Fleet rollout instead of direct apply."]
    if owner == K8sAppRef.OWNER_EXTERNAL:
        return ["External-owned resource: direct WebTerm mutation requires explicit ownership review."]
    return []


def _evidence(
    *, workload: K8sWorkloadRef | None, app: K8sAppRef | None, bundle: K8sFleetBundle | None, label_owner: str
) -> list[str]:
    evidence: list[str] = []
    if workload:
        evidence.append("matched_normalized_workload")
    if app:
        evidence.append(f"matched_{app.owner}_app")
    if bundle:
        evidence.append("matched_fleet_bundle")
    if label_owner:
        evidence.append(f"matched_{label_owner}_metadata")
    return evidence


def _workload_payload(workload: K8sWorkloadRef | None) -> dict[str, Any] | None:
    if not workload:
        return None
    return {
        "id": f"workload_{workload.id}",
        "name": workload.name,
        "namespace": workload.namespace,
        "kind": workload.kind,
        "owner": workload.owner,
        "team": workload.team,
        "health": workload.health,
        "version": workload.version,
        "labels": sanitize_metadata(workload.labels or {}),
        "links": sanitize_links(workload.links or {}),
    }


def _app_payload(app: K8sAppRef | None) -> dict[str, Any] | None:
    if not app:
        return None
    return {
        "id": f"app_{app.id}",
        "name": app.name,
        "namespace": app.namespace,
        "owner": app.owner,
        "team": app.team,
        "health": app.health,
        "version": app.version,
        "labels": sanitize_metadata(app.labels or {}),
        "links": sanitize_links(app.links or {}),
    }


def _bundle_payload(bundle: K8sFleetBundle | None) -> dict[str, Any] | None:
    if not bundle:
        return None
    return {
        "id": f"fleet_{bundle.id}",
        "name": bundle.name,
        "status": bundle.status,
        "source": bundle.source,
        "target": bundle.target,
        "labels": sanitize_metadata(bundle.labels or {}),
        "links": sanitize_links(bundle.links or {}),
    }


def _workload_kind(kind: str) -> str:
    aliases = {
        "deployment": K8sWorkloadRef.KIND_DEPLOYMENT,
        "statefulset": K8sWorkloadRef.KIND_STATEFULSET,
        "daemonset": K8sWorkloadRef.KIND_DAEMONSET,
        "cronjob": K8sWorkloadRef.KIND_CRONJOB,
        "job": K8sWorkloadRef.KIND_JOB,
        "pod": K8sWorkloadRef.KIND_POD,
    }
    return aliases.get(str(kind or "").lower(), "")
