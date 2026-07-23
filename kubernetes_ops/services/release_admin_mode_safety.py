from __future__ import annotations

from contextlib import contextmanager, suppress
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.services.admin_apply import apply_kubernetes_resource
from kubernetes_ops.services.admin_delete import delete_kubernetes_resource
from kubernetes_ops.services.admin_dry_run import dry_run_apply_kubernetes_resource
from kubernetes_ops.services.admin_exec import prepare_kubernetes_exec_bridge
from kubernetes_ops.services.admin_node_maintenance import run_node_maintenance_action
from kubernetes_ops.services.admin_patch import patch_kubernetes_resource
from kubernetes_ops.services.admin_port_forward import prepare_kubernetes_port_forward_bridge
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_workload_actions import restart_kubernetes_workload, scale_kubernetes_workload


def build_kubernetes_release_admin_mode_safety_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "Admin Mode safety proof skipped"}
    if not user or not getattr(user, "is_staff", False):
        return {"success": False, "status": "missing", "reason": "staff user is required for Admin Mode safety proof"}
    try:
        with transaction.atomic():
            _grant_admin_mode_features(user)
            provider = K8sProvider.objects.create(
                name="release-admin-mode-safety-rancher",
                kind=K8sProvider.KIND_RANCHER,
                base_url="https://rancher.release-safety.example.test",
                auth_mode=K8sProvider.AUTH_NONE,
            )
            cluster = K8sCluster.objects.create(
                name="release-admin-mode-safety",
                environment="test",
                rancher_provider=provider,
                rancher_cluster_id="c-release-admin-mode-safety",
            )
            prod_cluster = K8sCluster.objects.create(
                name="release-admin-mode-prod-safety",
                environment="prod",
                rancher_provider=provider,
                rancher_cluster_id="c-release-admin-mode-prod-safety",
            )
            proof = _run_admin_mode_safety_checks(user=user, cluster=cluster, prod_cluster=prod_cluster)
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def _run_admin_mode_safety_checks(*, user, cluster: K8sCluster, prod_cluster: K8sCluster) -> dict[str, Any]:
    provider_called = False
    initial_action_count = K8sAdminAction.objects.count()

    def fail_transport(*_args, **_kwargs):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider transport must not be called by Admin Mode safety proof")

    write_session = _unapproved_write_session(user=user, cluster=cluster)
    break_glass_session = _unapproved_break_glass_session(user=user, cluster=cluster)
    prod_write_session = _unapproved_write_session(user=user, cluster=prod_cluster)

    manifest = _deployment_manifest(namespace="release-safety")
    checks = []
    with _temporary_settings(
        KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True,
        KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
        KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["release-safety/service/release-api:8080"],
    ):
        checks.extend(
            [
                _expect_denied(
                    "dry_run_apply_unapproved",
                    "admin_session_approval_required",
                    lambda: dry_run_apply_kubernetes_resource(
                        user=user,
                        session_id=str(write_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        manifest=manifest,
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "apply_unapproved",
                    "admin_session_approval_required",
                    lambda: apply_kubernetes_resource(
                        user=user,
                        session_id=str(write_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        dry_run_action_id="",
                        reason="release Admin Mode safety apply smoke",
                        manifest=manifest,
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "patch_unapproved",
                    "admin_session_approval_required",
                    lambda: patch_kubernetes_resource(
                        user=user,
                        session_id=str(write_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        api_version="apps/v1",
                        kind="Deployment",
                        namespace="release-safety",
                        name="release-api",
                        patch_body={"metadata": {"labels": {"release-safety": "true"}}},
                        reason="release Admin Mode safety patch smoke",
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "scale_unapproved",
                    "admin_session_approval_required",
                    lambda: scale_kubernetes_workload(
                        user=user,
                        session_id=str(write_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        api_version="apps/v1",
                        kind="Deployment",
                        namespace="release-safety",
                        name="release-api",
                        replicas=2,
                        reason="release Admin Mode safety scale smoke",
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "restart_unapproved",
                    "admin_session_approval_required",
                    lambda: restart_kubernetes_workload(
                        user=user,
                        session_id=str(write_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        api_version="apps/v1",
                        kind="Deployment",
                        namespace="release-safety",
                        name="release-api",
                        reason="release Admin Mode safety restart smoke",
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "delete_unapproved",
                    "admin_session_approval_required",
                    lambda: delete_kubernetes_resource(
                        user=user,
                        session_id=str(write_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        api_version="apps/v1",
                        kind="Deployment",
                        namespace="release-safety",
                        name="release-api",
                        confirmation="delete Deployment release-safety/release-api",
                        reason="release Admin Mode safety delete smoke",
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "node_cordon_unapproved",
                    "admin_session_approval_required",
                    lambda: run_node_maintenance_action(
                        user=user,
                        session_id=str(break_glass_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        action="cordon",
                        node_name="release-worker-1",
                        reason="release Admin Mode safety node cordon smoke",
                        transport=fail_transport,
                    ),
                ),
                _expect_denied(
                    "exec_unapproved",
                    "admin_session_approval_required",
                    lambda: prepare_kubernetes_exec_bridge(
                        user=user,
                        session_id=str(break_glass_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        namespace="release-safety",
                        pod_name="release-api-abc123",
                        command="/bin/sh",
                        reason="release Admin Mode safety exec smoke",
                    ),
                ),
                _expect_denied(
                    "port_forward_unapproved",
                    "admin_session_approval_required",
                    lambda: prepare_kubernetes_port_forward_bridge(
                        user=user,
                        session_id=str(break_glass_session.session_id),
                        cluster_id=f"cluster_{cluster.id}",
                        namespace="release-safety",
                        kind="Service",
                        name="release-api",
                        remote_port=8080,
                        reason="release Admin Mode safety port-forward smoke",
                    ),
                ),
                _expect_denied(
                    "prod_write_unapproved",
                    "production_approval_required",
                    lambda: patch_kubernetes_resource(
                        user=user,
                        session_id=str(prod_write_session.session_id),
                        cluster_id=f"cluster_{prod_cluster.id}",
                        api_version="apps/v1",
                        kind="Deployment",
                        namespace="release-safety",
                        name="release-api",
                        patch_body={"metadata": {"labels": {"release-safety": "true"}}},
                        reason="release Admin Mode production safety smoke",
                        transport=fail_transport,
                    ),
                ),
            ]
        )

    created_action_count = K8sAdminAction.objects.count() - initial_action_count
    success = all(item["success"] for item in checks) and not provider_called and created_action_count == 0
    return {
        "success": success,
        "status": "ready" if success else "failed",
        "mode": "transaction_rollback",
        "checks": checks,
        "checked_count": len(checks),
        "provider_called": provider_called,
        "admin_actions_created": created_action_count,
        "persistent_rows": False,
    }


def _grant_admin_mode_features(user) -> None:
    for feature in ("kubernetes", "kubernetes_admin_write", "kubernetes_break_glass"):
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


def _unapproved_write_session(*, user, cluster: K8sCluster) -> K8sAdminSession:
    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        mode=K8sAdminSession.MODE_WRITE,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_HIGH,
        allowed_verbs=[
            "get",
            "list",
            "watch",
            "logs",
            "yaml",
            "dry_run_apply",
            "apply",
            "patch",
            "scale",
            "restart",
            "delete",
        ],
        allowed_kinds=["Deployment", "Service", "Ingress"],
        allowed_namespaces=["release-safety"],
        reason="release Admin Mode safety unapproved write session",
        expires_at=timezone.now() + timedelta(minutes=30),
    )


def _unapproved_break_glass_session(*, user, cluster: K8sCluster) -> K8sAdminSession:
    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        cluster=cluster,
        namespace="release-safety",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward", "cordon", "uncordon", "drain"],
        allowed_kinds=["pod", "service", "node"],
        allowed_namespaces=["release-safety"],
        reason="release Admin Mode safety unapproved break-glass session",
        expires_at=timezone.now() + timedelta(minutes=15),
    )


def _deployment_manifest(*, namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "release-api", "namespace": namespace},
        "spec": {"replicas": 1},
    }


def _expect_denied(name: str, expected_code: str, call) -> dict[str, Any]:
    try:
        call()
    except AdminResourceError as exc:
        return {
            "id": name,
            "success": exc.code == expected_code,
            "expected_code": expected_code,
            "actual_code": exc.code,
            "status": "blocked" if exc.code == expected_code else "unexpected_error_code",
        }
    except Exception as exc:
        return {
            "id": name,
            "success": False,
            "expected_code": expected_code,
            "actual_code": exc.__class__.__name__,
            "status": "unexpected_exception",
        }
    return {"id": name, "success": False, "expected_code": expected_code, "actual_code": "", "status": "not_blocked"}


@contextmanager
def _temporary_settings(**overrides):
    previous = {key: getattr(settings, key, None) for key in overrides}
    missing = {key for key in overrides if not hasattr(settings, key)}
    try:
        for key, value in overrides.items():
            setattr(settings, key, value)
        yield
    finally:
        for key in overrides:
            if key in missing:
                with suppress(AttributeError):
                    delattr(settings, key)
            else:
                setattr(settings, key, previous[key])
