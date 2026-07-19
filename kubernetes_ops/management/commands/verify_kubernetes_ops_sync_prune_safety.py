from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kubernetes_ops.models import (
    K8sCluster,
    K8sEvent,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)
from kubernetes_ops.services.sync import sync_rancher_provider


class Command(BaseCommand):
    help = "Verify Kubernetes Ops local inventory pruning only happens after successful provider sync."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print the full bounded JSON report.")
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when the proof fails.")

    def handle(self, *args, **options):
        report = verify_sync_prune_safety()
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self.stdout.write(
                "Kubernetes Ops sync prune safety: "
                f"status={report['status']} success_pruned={report['success_case']['stale_rows_pruned']} "
                f"failure_preserved={report['failure_case']['stale_rows_preserved']}"
            )
        if not report["success"] and not options["no_fail"]:
            raise CommandError("; ".join(report["errors"][:8]))


def verify_sync_prune_safety() -> dict[str, Any]:
    errors: list[str] = []
    try:
        with transaction.atomic():
            success_case = _successful_sync_prunes_stale_rows()
            failure_case = _failed_sync_preserves_stale_rows()
            transaction.set_rollback(True)
    except Exception as exc:
        return {
            "success": False,
            "status": "failed",
            "mode": "rollback_transaction",
            "success_case": {},
            "failure_case": {},
            "errors": [str(exc)],
        }

    if not success_case["stale_rows_pruned"]:
        errors.append("successful sync did not prune stale local inventory rows")
    if not success_case["fresh_rows_preserved"]:
        errors.append("successful sync did not preserve fresh local inventory rows")
    if not failure_case["stale_rows_preserved"]:
        errors.append("failed sync pruned stale local inventory rows")

    return {
        "success": not errors,
        "status": "ready" if not errors else "failed",
        "mode": "rollback_transaction",
        "success_case": success_case,
        "failure_case": failure_case,
        "errors": errors,
    }


def _successful_sync_prunes_stale_rows() -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:10]
    provider = K8sProvider.objects.create(
        name=f"prune-success-{suffix}",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher-prune-success.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = _create_stale_inventory(provider=provider, suffix=suffix)
    result = sync_rancher_provider(provider, transport=_successful_transport)
    cluster.refresh_from_db()
    stale_counts = _inventory_counts(cluster, prefix=f"stale-{suffix}")
    fresh_counts = _inventory_counts(cluster, prefix="fresh")
    return {
        "sync_success": result.success,
        "stale_rows_pruned": result.success and sum(stale_counts.values()) == 0,
        "fresh_rows_preserved": result.success and all(value == 1 for value in fresh_counts.values()),
        "stale_counts": stale_counts,
        "fresh_counts": fresh_counts,
    }


def _failed_sync_preserves_stale_rows() -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:10]
    provider = K8sProvider.objects.create(
        name=f"prune-failure-{suffix}",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher-prune-failure.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
    )
    cluster = _create_stale_inventory(provider=provider, suffix=suffix)
    result = sync_rancher_provider(provider, transport=_failing_transport)
    stale_counts = _inventory_counts(cluster, prefix=f"stale-{suffix}")
    return {
        "sync_success": result.success,
        "stale_rows_preserved": not result.success and all(value == 1 for value in stale_counts.values()),
        "stale_counts": stale_counts,
        "error_recorded": bool(result.error),
    }


def _create_stale_inventory(*, provider: K8sProvider, suffix: str) -> K8sCluster:
    cluster = K8sCluster.objects.create(
        name=f"prune-safety-cluster-{suffix}",
        rancher_provider=provider,
        rancher_cluster_id="prune-safety",
    )
    K8sNamespace.objects.create(cluster=cluster, name=f"stale-{suffix}-namespace")
    K8sWorkloadRef.objects.create(cluster=cluster, namespace="default", name=f"stale-{suffix}-workload")
    K8sPodRef.objects.create(cluster=cluster, namespace="default", name=f"stale-{suffix}-pod")
    K8sNetworkRef.objects.create(
        cluster=cluster,
        namespace="default",
        name=f"stale-{suffix}-service",
        kind=K8sNetworkRef.KIND_SERVICE,
    )
    K8sEvent.objects.create(cluster=cluster, event_uid=f"stale-{suffix}-event", reason="Stale")
    return cluster


def _inventory_counts(cluster: K8sCluster, *, prefix: str) -> dict[str, int]:
    return {
        "namespaces": K8sNamespace.objects.filter(cluster=cluster, name__startswith=prefix).count(),
        "workloads": K8sWorkloadRef.objects.filter(cluster=cluster, name__startswith=prefix).count(),
        "pods": K8sPodRef.objects.filter(cluster=cluster, name__startswith=prefix).count(),
        "network": K8sNetworkRef.objects.filter(cluster=cluster, name__startswith=prefix).count(),
        "events": K8sEvent.objects.filter(cluster=cluster, event_uid__startswith=prefix).count(),
    }


def _successful_transport(url: str, _headers: dict[str, str], _timeout: float) -> dict[str, Any]:
    if url.endswith("/v3/clusters"):
        return {"data": [{"id": "prune-safety", "name": "prune-safety-cluster", "state": "active"}]}
    if url.endswith("/v3/projectnamespaces"):
        return {"data": [{"id": "prune-safety:default", "name": "fresh-namespace", "clusterId": "prune-safety"}]}
    if url.endswith("/v3/workloads"):
        return {
            "data": [
                {
                    "id": "deployment:default:fresh-workload",
                    "name": "fresh-workload",
                    "clusterId": "prune-safety",
                    "namespaceId": "default",
                    "workloadType": "deployment",
                    "state": "active",
                }
            ]
        }
    if url.endswith("/v3/pods"):
        return {
            "data": [
                {
                    "id": "prune-safety:default:fresh-pod",
                    "name": "fresh-pod",
                    "clusterId": "prune-safety",
                    "namespaceId": "default",
                    "state": "Running",
                }
            ]
        }
    if url.endswith("/v3/services"):
        return {
            "data": [
                {
                    "id": "prune-safety:default:fresh-service",
                    "name": "fresh-service",
                    "clusterId": "prune-safety",
                    "namespaceId": "default",
                    "state": "active",
                }
            ]
        }
    if url.endswith("/v3/ingresses"):
        return {"data": []}
    if url.endswith("/v3/events"):
        return {
            "data": [
                {
                    "id": "fresh-event",
                    "clusterId": "prune-safety",
                    "namespace": "default",
                    "reason": "Scheduled",
                }
            ]
        }
    if url.endswith("/v1/fleet.cattle.io.bundles"):
        return {"data": []}
    raise AssertionError(url)


def _failing_transport(_url: str, _headers: dict[str, str], _timeout: float) -> dict[str, Any]:
    raise RuntimeError("simulated provider failure before prune")
