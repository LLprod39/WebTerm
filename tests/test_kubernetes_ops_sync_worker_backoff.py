from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.test import override_settings

from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.sync import KubernetesSyncResult
from servers.models import BackgroundWorkerState


@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS=25)
def test_kubernetes_ops_sync_worker_backs_off_after_repeated_failed_results(monkeypatch):
    calls = []
    sleeps = []

    def fake_sync(**kwargs):
        calls.append(kwargs)
        return [
            KubernetesSyncResult(
                provider_id=7,
                provider_name="rancher-main",
                provider_kind=K8sProvider.KIND_RANCHER,
                success=False,
                error="provider unavailable",
            )
        ]

    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync
    )
    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )
    out = io.StringIO()

    call_command(
        "run_kubernetes_ops_sync_worker",
        "--daemon",
        "--max-runs",
        "3",
        "--interval",
        "10",
        "--worker-key",
        "pytest-k8s-sync-backoff",
        stdout=out,
    )

    assert len(calls) == 3
    assert sleeps == [10, 20]
    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-backoff",
    )
    assert state.last_summary["failed"] == 1
    assert state.last_summary["consecutive_failures"] == 3
    assert state.last_summary["last_error"] == "provider unavailable"
    assert "failure backoff" in out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_kubernetes_ops_sync_worker_resets_backoff_after_success(monkeypatch):
    sleeps = []
    results = [
        [KubernetesSyncResult(1, "rancher-main", K8sProvider.KIND_RANCHER, False, error="first failure")],
        [KubernetesSyncResult(1, "rancher-main", K8sProvider.KIND_RANCHER, False, error="second failure")],
        [KubernetesSyncResult(1, "rancher-main", K8sProvider.KIND_RANCHER, True, clusters=1)],
    ]

    def fake_sync(**kwargs):
        return results.pop(0)

    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync
    )
    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    call_command(
        "run_kubernetes_ops_sync_worker",
        "--daemon",
        "--max-runs",
        "3",
        "--interval",
        "5",
        "--worker-key",
        "pytest-k8s-sync-backoff-reset",
    )

    assert sleeps == [5, 10]
    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-backoff-reset",
    )
    assert state.last_summary["ok"] == 1
    assert state.last_summary["failed"] == 0
    assert state.last_summary["consecutive_failures"] == 0


@pytest.mark.django_db(transaction=True)
def test_kubernetes_ops_sync_worker_backoff_counts_exceptions_toward_max_runs(monkeypatch):
    sleeps = []

    def fake_sync(**kwargs):
        raise RuntimeError("provider transport exploded")

    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync
    )
    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    call_command(
        "run_kubernetes_ops_sync_worker",
        "--daemon",
        "--max-runs",
        "2",
        "--interval",
        "3",
        "--worker-key",
        "pytest-k8s-sync-backoff-exception",
    )

    assert sleeps == [3]
    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-backoff-exception",
    )
    assert state.status == BackgroundWorkerState.STATUS_ERROR
    assert state.last_summary["errors"] == 2
    assert state.last_summary["consecutive_failures"] == 2
    assert "provider transport exploded" in state.last_error
