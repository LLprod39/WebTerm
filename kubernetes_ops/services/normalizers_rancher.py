from __future__ import annotations

from typing import Any

from kubernetes_ops.models import (
    K8sAppRef,
    K8sCluster,
    K8sFleetBundle,
    K8sNetworkRef,
    K8sProvider,
)
from kubernetes_ops.services.normalizers_base import (
    as_int,
    as_list,
    bounded_text,
    compact_strings,
    first_value,
    infer_environment,
    labels_for,
    nested,
    normalize_event_severity,
    normalize_fleet_status,
    normalize_health,
    normalize_workload_kind,
    parse_event_time,
    split_rancher_ref,
)


def _first_dict(values: list[Any]) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _pod_health(phase: str, restart_count: int, container_statuses: list[Any]) -> str:
    waiting_reasons = [
        str(nested(status, "state", "waiting", "reason") or "").lower()
        for status in container_statuses
        if isinstance(status, dict)
    ]
    if any(
        reason in {"crashloopbackoff", "imagepullbackoff", "errimagepull", "createcontainerconfigerror"}
        for reason in waiting_reasons
    ):
        return K8sCluster.HEALTH_DEGRADED
    if any(reason in {"containercreating", "podinitializing"} for reason in waiting_reasons):
        return K8sCluster.HEALTH_WARNING
    if phase.lower() in {"running", "succeeded", "completed"}:
        return K8sCluster.HEALTH_WARNING if restart_count else K8sCluster.HEALTH_HEALTHY
    return normalize_health(phase)


def normalize_rancher_cluster(provider: K8sProvider, item: dict[str, Any]) -> dict[str, Any]:
    labels = labels_for(item)
    cluster_id = str(first_value(item, "id", "metadata.name", "name")).strip()
    name = str(first_value(item, "name", "metadata.name", default=cluster_id)).strip()
    state = first_value(item, "state", "status", "health", "status.phase", "status.state")
    total = as_int(first_value(item, "nodeCount", "nodes_total", "status.nodeCount", "status.nodesTotal"))
    ready = as_int(
        first_value(item, "readyNodes", "nodes_ready", "nodeReadyCount", "status.readyNodes", "status.nodesReady")
    )
    health = normalize_health(state)
    if health == K8sCluster.HEALTH_HEALTHY and total and not ready:
        ready = total
    return {
        "name": name or cluster_id,
        "environment": infer_environment(name or cluster_id, labels, str(first_value(item, "environment", "env"))),
        "health": health,
        "rancher_provider": provider,
        "rancher_cluster_id": cluster_id,
        "nodes_ready": ready,
        "nodes_total": total,
        "namespace_count": as_int(first_value(item, "namespaceCount", "namespaces", "status.namespaceCount")),
        "workload_count": as_int(first_value(item, "workloadCount", "workloads", "status.workloadCount")),
        "labels": labels,
        "links": {"rancher": str(first_value(item, "links.self", "url", default=""))},
    }


def normalize_rancher_namespace(item: dict[str, Any]) -> dict[str, Any]:
    labels = labels_for(item)
    raw_id = str(first_value(item, "id", "metadata.name", "name")).strip()
    id_parts = split_rancher_ref(raw_id)
    project_ref = first_value(item, "projectId", "project_id") or labels.get("field.cattle.io/projectId")
    project_parts = split_rancher_ref(project_ref)
    cluster_id = str(first_value(item, "clusterId", "cluster_id", "cluster.id", default="")).strip()
    if not cluster_id and project_parts:
        cluster_id = project_parts[0]
    if not cluster_id and len(id_parts) > 1:
        cluster_id = id_parts[0]
    name = str(first_value(item, "name", "namespace", "metadata.name", default="")).strip()
    if (not name or name == raw_id) and id_parts:
        name = id_parts[-1]
    cluster_name = str(first_value(item, "clusterName", "cluster_name", "cluster.name", default=cluster_id)).strip()
    state = first_value(item, "state", "status", "status.phase", "status.state")
    return {
        "cluster_rancher_id": cluster_id,
        "cluster_name": cluster_name or cluster_id or "rancher",
        "name": name or raw_id or "default",
        "environment": infer_environment(name or raw_id, labels, str(first_value(item, "environment", "env"))),
        "health": normalize_health(state),
        "app_count": as_int(first_value(item, "appCount", "apps", "status.appCount")),
        "workload_count": as_int(first_value(item, "workloadCount", "workloads", "status.workloadCount")),
        "labels": labels,
        "links": {"rancher": str(first_value(item, "links.self", "url", default=""))},
    }


def normalize_rancher_workload(item: dict[str, Any]) -> dict[str, Any]:
    labels = labels_for(item)
    raw_id = str(first_value(item, "id", "metadata.name", "name")).strip()
    id_parts = split_rancher_ref(raw_id)
    cluster_id = str(first_value(item, "clusterId", "cluster_id", "cluster.id", default="")).strip()
    project_ref = first_value(item, "projectId", "project_id") or labels.get("field.cattle.io/projectId")
    project_parts = split_rancher_ref(project_ref)
    if not cluster_id and project_parts:
        cluster_id = project_parts[0]
    namespace = str(first_value(item, "namespaceId", "namespace", "metadata.namespace", default="")).strip()
    if not namespace and len(id_parts) >= 2:
        namespace = id_parts[-2]
    name = str(first_value(item, "name", "metadata.name", default="")).strip()
    if (not name or name == raw_id) and id_parts:
        name = id_parts[-1]
    kind = normalize_workload_kind(
        first_value(item, "workloadType", "kind", "type", default=id_parts[0] if id_parts else "")
    )
    cluster_name = str(first_value(item, "clusterName", "cluster_name", "cluster.name", default=cluster_id)).strip()
    desired = as_int(first_value(item, "scale", "replicas", "desired", "spec.replicas", "status.replicas"))
    ready = as_int(
        first_value(
            item, "readyReplicas", "availableReplicas", "ready", "status.readyReplicas", "status.availableReplicas"
        )
    )
    health = normalize_health(first_value(item, "state", "status.phase", "status.state", "status"))
    if health == K8sCluster.HEALTH_UNKNOWN and desired:
        health = K8sCluster.HEALTH_HEALTHY if ready >= desired else K8sCluster.HEALTH_DEGRADED
    return {
        "cluster_rancher_id": cluster_id,
        "cluster_name": cluster_name or cluster_id or "rancher",
        "namespace": namespace or "default",
        "name": name or raw_id,
        "kind": kind,
        "environment": infer_environment(
            namespace or name or raw_id, labels, str(first_value(item, "environment", "env"))
        ),
        "owner": str(labels.get("app.kubernetes.io/managed-by") or labels.get("owner") or "rancher"),
        "team": str(labels.get("webterm.io/team") or labels.get("team") or ""),
        "health": health,
        "ready": ready,
        "desired": desired,
        "version": str(first_value(item, "imageTag", "image", "version", "status.image", default="")).strip(),
        "links": {"rancher": str(first_value(item, "links.self", "url", default=""))},
        "labels": labels,
    }


def normalize_rancher_pod(item: dict[str, Any]) -> dict[str, Any]:
    labels = labels_for(item)
    raw_id = str(first_value(item, "id", "metadata.name", "name")).strip()
    id_parts = split_rancher_ref(raw_id)
    cluster_id = str(first_value(item, "clusterId", "cluster_id", "cluster.id", default="")).strip()
    project_ref = first_value(item, "projectId", "project_id") or labels.get("field.cattle.io/projectId")
    project_parts = split_rancher_ref(project_ref)
    if not cluster_id and project_parts:
        cluster_id = project_parts[0]
    namespace = str(first_value(item, "namespaceId", "namespace", "metadata.namespace", default="")).strip()
    if not namespace and len(id_parts) >= 2:
        namespace = id_parts[-2]
    name = str(first_value(item, "name", "metadata.name", default="")).strip()
    if (not name or name == raw_id) and id_parts:
        name = id_parts[-1]
    cluster_name = str(first_value(item, "clusterName", "cluster_name", "cluster.name", default=cluster_id)).strip()
    owner = _first_dict(as_list(first_value(item, "ownerReferences", "metadata.ownerReferences", default=[])))
    container_statuses = as_list(first_value(item, "containerStatuses", "status.containerStatuses", default=[]))
    containers = as_list(first_value(item, "containers", "spec.containers", default=[]))
    restart_count = sum(as_int(status.get("restartCount")) for status in container_statuses if isinstance(status, dict))
    images = compact_strings(
        [
            *(status.get("image") for status in container_statuses if isinstance(status, dict)),
            *(container.get("image") for container in containers if isinstance(container, dict)),
        ],
        limit=10,
    )
    phase = str(first_value(item, "state", "phase", "status.phase", "status.state", default="")).strip()
    total_containers = len(container_statuses) or len(containers)
    ready_containers = sum(1 for status in container_statuses if isinstance(status, dict) and bool(status.get("ready")))
    return {
        "cluster_rancher_id": cluster_id,
        "cluster_name": cluster_name or cluster_id or "rancher",
        "namespace": namespace or "default",
        "name": name or raw_id,
        "environment": infer_environment(
            namespace or name or raw_id, labels, str(first_value(item, "environment", "env"))
        ),
        "health": _pod_health(phase, restart_count, container_statuses),
        "phase": phase,
        "node_name": str(first_value(item, "nodeName", "spec.nodeName", default="")).strip(),
        "pod_ip": str(first_value(item, "podIp", "podIP", "status.podIP", default="")).strip(),
        "host_ip": str(first_value(item, "hostIp", "hostIP", "status.hostIP", default="")).strip(),
        "owner_kind": str(owner.get("kind") or "").strip(),
        "owner_name": str(owner.get("name") or "").strip(),
        "ready_containers": ready_containers,
        "total_containers": total_containers,
        "restart_count": restart_count,
        "images": images,
        "links": {
            "rancher": str(first_value(item, "links.self", "url", default="")),
            "logs": str(first_value(item, "logsUrl", "logs_url", "links.logs", default="")),
        },
        "labels": labels,
    }


def _network_base(item: dict[str, Any]) -> tuple[dict[str, Any], str, str, str, str, str]:
    labels = labels_for(item)
    raw_id = str(first_value(item, "id", "metadata.name", "name")).strip()
    id_parts = split_rancher_ref(raw_id)
    cluster_id = str(first_value(item, "clusterId", "cluster_id", "cluster.id", default="")).strip()
    project_ref = first_value(item, "projectId", "project_id") or labels.get("field.cattle.io/projectId")
    project_parts = split_rancher_ref(project_ref)
    if not cluster_id and project_parts:
        cluster_id = project_parts[0]
    namespace = str(first_value(item, "namespaceId", "namespace", "metadata.namespace", default="")).strip()
    if not namespace and len(id_parts) >= 2:
        namespace = id_parts[-2]
    name = str(first_value(item, "name", "metadata.name", default="")).strip()
    if (not name or name == raw_id) and id_parts:
        name = id_parts[-1]
    cluster_name = str(first_value(item, "clusterName", "cluster_name", "cluster.name", default=cluster_id)).strip()
    return labels, raw_id, cluster_id, namespace or "default", cluster_name or cluster_id or "rancher", name or raw_id


def normalize_rancher_service(item: dict[str, Any]) -> dict[str, Any]:
    labels, raw_id, cluster_id, namespace, cluster_name, name = _network_base(item)
    ports = first_value(item, "ports", "spec.ports", default=[])
    endpoints = first_value(item, "publicEndpoints", "status.loadBalancer.ingress", "endpoints", default=[])
    health = normalize_health(first_value(item, "state", "status.phase", "status.state", "status"))
    if health == K8sCluster.HEALTH_UNKNOWN:
        health = K8sCluster.HEALTH_HEALTHY
    return {
        "cluster_rancher_id": cluster_id,
        "cluster_name": cluster_name,
        "namespace": namespace,
        "name": name,
        "kind": K8sNetworkRef.KIND_SERVICE,
        "environment": infer_environment(
            namespace or name or raw_id, labels, str(first_value(item, "environment", "env"))
        ),
        "health": health,
        "service_type": str(first_value(item, "serviceType", "type", "spec.type", default="")).strip(),
        "ports": as_list(ports),
        "hosts": [],
        "endpoints": as_list(endpoints),
        "links": {"rancher": str(first_value(item, "links.self", "url", default=""))},
        "labels": labels,
    }


def normalize_rancher_ingress(item: dict[str, Any]) -> dict[str, Any]:
    labels, raw_id, cluster_id, namespace, cluster_name, name = _network_base(item)
    rules = as_list(first_value(item, "rules", "spec.rules", default=[]))
    hosts = compact_strings([rule.get("host") for rule in rules if isinstance(rule, dict)])
    explicit_host = str(first_value(item, "host", "hostname", "fqdn", default="")).strip()
    if explicit_host and explicit_host not in hosts:
        hosts.insert(0, explicit_host)
    endpoints = first_value(item, "publicEndpoints", "status.loadBalancer.ingress", "backends", default=[])
    health = normalize_health(first_value(item, "state", "status.phase", "status.state", "status"))
    if health == K8sCluster.HEALTH_UNKNOWN:
        health = K8sCluster.HEALTH_HEALTHY
    return {
        "cluster_rancher_id": cluster_id,
        "cluster_name": cluster_name,
        "namespace": namespace,
        "name": name,
        "kind": K8sNetworkRef.KIND_INGRESS,
        "environment": infer_environment(
            namespace or name or raw_id, labels, str(first_value(item, "environment", "env"))
        ),
        "health": health,
        "service_type": str(first_value(item, "ingressClassName", "spec.ingressClassName", default="")).strip(),
        "ports": as_list(first_value(item, "ports", default=[])),
        "hosts": hosts,
        "endpoints": as_list(endpoints),
        "links": {"rancher": str(first_value(item, "links.self", "url", default=""))},
        "labels": labels,
    }


def normalize_rancher_event(item: dict[str, Any]) -> dict[str, Any]:
    labels = labels_for(item)
    involved = nested(item, "involvedObject") or {}
    event_uid = str(first_value(item, "uid", "metadata.uid", "id", "name")).strip()
    cluster_id = str(first_value(item, "clusterId", "cluster_id", "cluster.id", default="")).strip()
    namespace = str(first_value(item, "namespace", "metadata.namespace", default="")).strip()
    if isinstance(involved, dict):
        cluster_id = cluster_id or str(involved.get("clusterId") or "")
        namespace = namespace or str(involved.get("namespace") or "")
    id_parts = split_rancher_ref(event_uid)
    if not cluster_id and len(id_parts) > 1:
        cluster_id = id_parts[0]
    cluster_name = str(first_value(item, "clusterName", "cluster_name", "cluster.name", default=cluster_id)).strip()
    event_type = first_value(item, "type", "eventType", "metadata.type", default="")
    reason = str(first_value(item, "reason", "metadata.reason", default="")).strip()
    return {
        "cluster_rancher_id": cluster_id,
        "cluster_name": cluster_name or cluster_id or "rancher",
        "event_uid": event_uid
        or f"{cluster_id}:{namespace}:{reason}:{first_value(item, 'lastTimestamp', 'eventTime', 'created')}",
        "source": bounded_text(
            first_value(item, "source.component", "reportingComponent", "source", default="rancher"), 80
        )
        or "rancher",
        "severity": normalize_event_severity(event_type or reason),
        "reason": reason or str(first_value(item, "name", "metadata.name", default="")).strip(),
        "message": str(first_value(item, "message", "note", "description", default="")).strip(),
        "namespace": namespace,
        "involved_kind": bounded_text(
            involved.get("kind") if isinstance(involved, dict) else first_value(item, "involvedKind", default=""), 80
        ),
        "involved_name": bounded_text(
            involved.get("name") if isinstance(involved, dict) else first_value(item, "involvedName", default=""), 180
        ),
        "count": as_int(first_value(item, "count", "series.count", default=1), default=1) or 1,
        "first_seen_at": parse_event_time(
            first_value(item, "firstTimestamp", "eventTime", "metadata.creationTimestamp")
        ),
        "last_seen_at": parse_event_time(first_value(item, "lastTimestamp", "eventTime", "metadata.creationTimestamp")),
        "labels": labels,
    }


def normalize_fleet_bundle(provider: K8sProvider, item: dict[str, Any]) -> dict[str, Any]:
    metadata_name = str(first_value(item, "metadata.name", "id", "name")).strip()
    namespace = str(first_value(item, "metadata.namespace", default="")).strip()
    name = f"{namespace}/{metadata_name}" if namespace and "/" not in metadata_name else metadata_name
    summary = nested(item, "status", "summary") or {}
    ready = as_int(first_value(item, "ready", "status.ready", "status.summary.ready", "status.summary.desiredReady"))
    desired = as_int(
        first_value(item, "desired", "status.desired", "status.summary.desired", "status.summary.desiredReady")
    )
    not_ready = as_int(summary.get("notReady") if isinstance(summary, dict) else 0)
    if not desired and ready:
        desired = ready + not_ready
    status = normalize_fleet_status(first_value(item, "status.display.state", "status.state", "status", "state"))
    if status == K8sFleetBundle.STATUS_UNKNOWN and desired:
        status = K8sFleetBundle.STATUS_READY if ready >= desired else K8sFleetBundle.STATUS_DEGRADED
    return {
        "name": name,
        "source": str(first_value(item, "source", "spec.repo", "spec.helm.chart", "spec.chart")),
        "target": str(first_value(item, "target", "spec.targetNamespace", "spec.targets", default="")),
        "status": status,
        "ready": ready,
        "desired": desired,
        "partitions": first_value(item, "partitions", "status.partitions", "status.summary.partitions", default=[]),
        "labels": labels_for(item),
        "links": {"rancher_fleet": str(first_value(item, "links.self", "url", default=""))},
    }


def normalize_devtron_app(item: dict[str, Any]) -> dict[str, Any]:
    cluster_name = str(
        first_value(
            item,
            "cluster_name",
            "clusterName",
            "environment.clusterName",
            "environmentDetail.clusterName",
            default="devtron",
        )
    ).strip()
    app_name = str(first_value(item, "appName", "name", "applicationName", default="")).strip()
    namespace = str(
        first_value(
            item,
            "namespace",
            "namespaceName",
            "environment.namespace",
            "environmentDetail.namespace",
            default="default",
        )
    ).strip()
    env = str(first_value(item, "environment", "environmentName", "envName", "env", default="")).strip()
    return {
        "cluster_name": cluster_name or "devtron",
        "devtron_cluster_id": str(
            first_value(
                item, "clusterId", "cluster_id", "environment.clusterId", "environmentDetail.clusterId", default=""
            )
        ).strip(),
        "name": app_name,
        "namespace": namespace or "default",
        "environment": infer_environment(cluster_name, labels_for(item), env),
        "owner": K8sAppRef.OWNER_DEVTRON,
        "team": str(first_value(item, "team", "teamName", "projectName", default="")).strip(),
        "health": normalize_health(
            first_value(item, "health", "status", "appStatus", "resourceTree.status", default="")
        ),
        "version": str(
            first_value(item, "version", "releaseVersion", "deployedVersion", "imageTag", "chartName", default="")
        ).strip(),
        "links": {
            "devtron_app": str(first_value(item, "url", "links.self", default="")),
            "logs": str(first_value(item, "logsUrl", "logs_url", "links.logs", default="")),
            "history": str(first_value(item, "historyUrl", "history_url", "links.history", default="")),
            "values": str(first_value(item, "valuesUrl", "values_url", "links.values", default="")),
        },
        "labels": labels_for(item),
    }
