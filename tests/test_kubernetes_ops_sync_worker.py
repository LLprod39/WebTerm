from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.test import override_settings

from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import (
    K8sProvider,
)
from kubernetes_ops.services.sync import KubernetesSyncResult
from servers.models import BackgroundWorkerState


@pytest.mark.django_db(transaction=True)
def test_kubernetes_ops_sync_worker_once_updates_background_state(monkeypatch):
    def fake_sync(**kwargs):
        assert kwargs["provider_id"] is None
        assert kwargs["kind"] == ""
        assert kwargs["dry_run"] is True
        return [
            KubernetesSyncResult(
                provider_id=1,
                provider_name="rancher-main",
                provider_kind=K8sProvider.KIND_RANCHER,
                success=True,
                clusters=2,
                fleet_bundles=1,
                dry_run=True,
            )
        ]

    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync
    )
    out = io.StringIO()

    call_command("run_kubernetes_ops_sync_worker", "--once", "--dry-run", "--worker-key", "pytest-k8s-sync", stdout=out)

    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert "run_kubernetes_ops_sync_worker" in state.command
    assert state.last_cycle_started_at is not None
    assert state.last_cycle_finished_at is not None
    assert state.last_summary["matched"] == 1
    assert state.last_summary["clusters"] == 2
    assert state.last_summary["namespaces"] == 0
    assert state.last_summary["workloads"] == 0
    assert state.last_summary["pods"] == 0
    assert state.last_summary["services"] == 0
    assert state.last_summary["ingresses"] == 0
    assert state.last_summary["events"] == 0
    assert state.last_summary["fleet_bundles"] == 1
    assert state.last_summary["dry_run"] is True
    assert "matched=1" in out.getvalue()


@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_OPS_SYNC_INTERVAL_SECONDS=42)
def test_kubernetes_ops_sync_worker_defaults_interval_from_settings(monkeypatch):
    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", lambda **_: []
    )

    call_command("run_kubernetes_ops_sync_worker", "--once", "--dry-run", "--worker-key", "pytest-k8s-sync-settings")

    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-settings",
    )
    assert "--interval 42" in state.command


@pytest.mark.django_db(transaction=True)
def test_kubernetes_ops_sync_worker_max_runs_repeats_with_filters(monkeypatch):
    calls = []

    def fake_sync(**kwargs):
        calls.append(kwargs)
        return [
            KubernetesSyncResult(
                provider_id=7,
                provider_name="devtron-main",
                provider_kind=K8sProvider.KIND_DEVTRON,
                success=True,
                clusters=1,
                apps=4,
            )
        ]

    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.sync_kubernetes_providers", fake_sync
    )
    monkeypatch.setattr(
        "kubernetes_ops.management.commands.run_kubernetes_ops_sync_worker.time.sleep", lambda _seconds: None
    )

    call_command(
        "run_kubernetes_ops_sync_worker",
        "--daemon",
        "--max-runs",
        "2",
        "--interval",
        "0",
        "--provider-id",
        "7",
        "--kind",
        K8sProvider.KIND_DEVTRON,
        "--worker-key",
        "pytest-k8s-sync-loop",
    )

    assert calls == [
        {"provider_id": 7, "kind": K8sProvider.KIND_DEVTRON, "dry_run": False},
        {"provider_id": 7, "kind": K8sProvider.KIND_DEVTRON, "dry_run": False},
    ]
    state = BackgroundWorkerState.objects.get(
        worker_kind=KUBERNETES_OPS_SYNC_WORKER,
        worker_key="pytest-k8s-sync-loop",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_summary["matched"] == 1
    assert state.last_summary["apps"] == 4
