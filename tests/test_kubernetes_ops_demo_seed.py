from __future__ import annotations

import io
import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import K8sAppRef, K8sCluster, K8sEvent, K8sFleetBundle, K8sProvider
from kubernetes_ops.services.release_readiness_summary import build_kubernetes_release_readiness_summary
from servers.models import BackgroundWorkerState


@pytest.mark.django_db
def test_seed_kubernetes_ops_demo_creates_safe_idempotent_inventory():
    user = User.objects.create_user(username="admin", password="x", is_staff=True)

    first_stdout = io.StringIO()
    call_command("seed_kubernetes_ops_demo", "--username", user.username, "--json", stdout=first_stdout)
    second_stdout = io.StringIO()
    call_command("seed_kubernetes_ops_demo", "--username", user.username, "--json", stdout=second_stdout)

    payload = json.loads(second_stdout.getvalue())

    assert payload["success"] is True
    assert payload["cluster"] == "webterm-k8s-demo"
    assert payload["demo_counts"] == {
        "clusters": 1,
        "providers": 2,
        "namespaces": 3,
        "workloads": 5,
        "apps": 3,
        "pods": 4,
        "network_refs": 3,
        "fleet_bundles": 2,
        "events": 2,
    }
    assert K8sCluster.objects.count() == 1
    assert K8sAppRef.objects.count() == 3
    assert K8sFleetBundle.objects.count() == 2
    assert K8sEvent.objects.count() == 2
    assert not K8sProvider.objects.exclude(secret_ref="").exists()
    assert set(K8sProvider.objects.values_list("base_url", flat=True)) == {"http://127.0.0.1:18090"}
    assert set(
        UserAppPermission.objects.filter(user=user, allowed=True).values_list("feature", flat=True)
    ) == {"kubernetes", "kubernetes_admin_read"}
    worker = BackgroundWorkerState.objects.get(worker_kind=KUBERNETES_OPS_SYNC_WORKER, worker_key="local-demo")
    assert worker.status == BackgroundWorkerState.STATUS_RUNNING
    assert worker.lease_expires_at is not None
    assert worker.lease_expires_at - timezone.now() > timedelta(hours=23)

    client = Client()
    client.force_login(user)
    response = client.get(reverse("api_kubernetes_overview"))

    assert response.status_code == 200
    overview = response.json()
    assert overview["summary"]["clusters"] == 1
    assert overview["summary"]["apps"] == 3
    assert overview["summary"]["fleet_rollouts"] == 2
    assert overview["summary"]["warnings"] == 2
    assert overview["summary"]["provider_issues"] == 0
    assert overview["access_policy"]["can_read"] is True
    assert overview["access_policy"]["can_admin_read"] is True
    assert all(provider["has_secret_ref"] is False for provider in overview["providers"])
    assert "vault://" not in str(overview)

    release_summary = build_kubernetes_release_readiness_summary(user=user)
    assert release_summary["backend_workstream"]["remaining_backend_gaps"] == []
    assert release_summary["backend_workstream"]["status"] == "backend_ready_production_blocked"


@pytest.mark.django_db
def test_seed_kubernetes_ops_demo_can_grant_explicit_admin_write_for_local_testing():
    user = User.objects.create_user(username="admin", password="x", is_staff=True)

    stdout = io.StringIO()
    call_command("seed_kubernetes_ops_demo", "--username", user.username, "--admin-write", "--json", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    granted = {item["feature"]: item["allowed"] for item in payload["user"]["granted"]}
    explicit = dict(UserAppPermission.objects.filter(user=user).values_list("feature", "allowed"))

    assert granted == {
        "kubernetes": True,
        "kubernetes_admin_read": True,
        "kubernetes_admin_write": True,
    }
    assert explicit["kubernetes_admin_write"] is True
    assert "kubernetes_break_glass" not in explicit
    assert "kubernetes_secret_read" not in explicit
