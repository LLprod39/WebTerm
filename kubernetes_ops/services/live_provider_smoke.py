from __future__ import annotations

import json
import urllib.parse
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from app.egress_redaction import redact_egress_text
from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sPodRef, K8sProvider
from kubernetes_ops.services.admin_logs import get_admin_pod_log_snapshot
from kubernetes_ops.services.admin_node_drain import build_node_drain_preflight
from kubernetes_ops.services.admin_resource_describe import get_cluster_resource_live_describe
from kubernetes_ops.services.admin_resources import (
    KubernetesResourceRef,
    get_cluster_resource_yaml,
    rancher_resource_path,
)
from kubernetes_ops.services.provider_probe import probe_kubernetes_provider, probe_result_payload
from kubernetes_ops.services.sync import KubernetesSyncResult, sync_kubernetes_providers

LIVE_PROVIDER_SMOKE_SCHEMA_VERSION = "kubernetes_ops.live_provider_smoke.v3"
LIVE_PROVIDER_SMOKE_ARTIFACT = "artifacts/kubernetes_ops_live_provider_smoke.json"
RANCHER_REQUIRED_COUNTS = ("clusters", "namespaces", "workloads", "pods")
DEVTRON_REQUIRED_COUNTS = ("apps",)


def build_kubernetes_live_provider_smoke(
    *,
    run_provider_probe: bool = True,
    run_sync_dry_run: bool = True,
    require_rancher: bool = True,
    require_devtron: bool = True,
    require_fleet: bool = True,
    run_backend_paths: bool = True,
    require_backend_paths: bool = True,
) -> dict[str, Any]:
    providers = list(K8sProvider.objects.filter(enabled=True).order_by("kind", "name"))
    provider_probes = _provider_probe_evidence(providers, run_provider_probe)
    sync_dry_run = _sync_dry_run_evidence(run_sync_dry_run)
    backend_paths = _backend_path_evidence(run_backend_paths)
    errors = _provider_requirement_errors(providers, require_rancher=require_rancher, require_devtron=require_devtron)
    errors.extend(_provider_probe_errors(provider_probes))
    errors.extend(_sync_dry_run_errors(sync_dry_run, require_fleet=require_fleet))
    errors.extend(_backend_path_errors(backend_paths, require_backend_paths=require_backend_paths))
    errors = list(dict.fromkeys(errors))
    status = "ready" if not errors else ("missing" if any("missing" in item for item in errors) else "failed")
    return {
        "schema_version": LIVE_PROVIDER_SMOKE_SCHEMA_VERSION,
        "status": status,
        "success": status == "ready",
        "checked_at": timezone.now().isoformat(),
        "summary": _summary(
            providers=providers,
            provider_probes=provider_probes,
            sync_dry_run=sync_dry_run,
            backend_paths=backend_paths,
        ),
        "requirements": {
            "require_rancher": require_rancher,
            "require_devtron": require_devtron,
            "require_fleet": require_fleet,
            "require_backend_paths": require_backend_paths,
            "run_provider_probe": run_provider_probe,
            "run_sync_dry_run": run_sync_dry_run,
            "run_backend_paths": run_backend_paths,
        },
        "providers": [_provider_summary(provider) for provider in providers],
        "provider_probes": provider_probes,
        "sync_dry_run": sync_dry_run,
        "backend_paths": backend_paths,
        "errors": errors,
    }


def write_live_provider_smoke(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _provider_summary(provider: K8sProvider) -> dict[str, Any]:
    return {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "provider_kind": provider.kind,
        "enabled": provider.enabled,
        "auth_mode": provider.auth_mode,
        "provider_base_url": _public_base_url(provider.base_url),
    }


def _provider_probe_evidence(providers: list[K8sProvider], enabled: bool) -> list[dict[str, Any]]:
    if not enabled:
        return [{"status": "skipped", "success": False, "reason": "provider probe skipped"}]
    if not providers:
        return [{"status": "missing", "success": False, "reason": "no enabled providers"}]
    results: list[dict[str, Any]] = []
    for provider in providers:
        payload = probe_result_payload(probe_kubernetes_provider(provider))
        payload["path"] = _public_path(str(payload.get("path") or ""))
        payload["error"] = _redacted_text(payload.get("error"))
        payload["provider_base_url"] = _public_base_url(provider.base_url)
        results.append(payload)
    return results


def _sync_dry_run_evidence(enabled: bool) -> list[dict[str, Any]]:
    if not enabled:
        return [{"status": "skipped", "success": False, "reason": "sync dry-run skipped"}]
    results = sync_kubernetes_providers(dry_run=True)
    if not results:
        return [{"status": "missing", "success": False, "reason": "no enabled providers matched sync"}]
    return [_sync_result_payload(item) for item in results]


def _sync_result_payload(result: KubernetesSyncResult) -> dict[str, Any]:
    return {
        "provider_id": result.provider_id,
        "provider_name": result.provider_name,
        "provider_kind": result.provider_kind,
        "success": result.success,
        "status": "ready" if result.success else "failed",
        "dry_run": result.dry_run,
        "clusters": result.clusters,
        "namespaces": result.namespaces,
        "workloads": result.workloads,
        "pods": result.pods,
        "services": result.services,
        "ingresses": result.ingresses,
        "events": result.events,
        "apps": result.apps,
        "fleet_bundles": result.fleet_bundles,
        "error": _redacted_text(result.error),
    }


def _backend_path_evidence(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"status": "skipped", "success": False, "reason": "backend path smoke skipped", "checks": []}
    pod = _backend_path_target_pod()
    if pod is None:
        return {
            "status": "missing",
            "success": False,
            "reason": "no synced Rancher pod target is available",
            "target": {},
            "checks": [],
        }
    try:
        with transaction.atomic():
            user = _backend_path_user()
            session = K8sAdminSession.objects.create(
                user=user,
                username_snapshot=user.username,
                provider=pod.cluster.rancher_provider,
                cluster=pod.cluster,
                mode=K8sAdminSession.MODE_READ,
                status=K8sAdminSession.STATUS_ACTIVE,
                risk_tier=K8sAdminSession.RISK_LOW,
                reason="live provider smoke backend path proof",
                allowed_verbs=["get", "list", "watch", "logs", "yaml"],
                allowed_kinds=["*"],
                allowed_namespaces=["*"],
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            break_glass_session = K8sAdminSession.objects.create(
                user=user,
                username_snapshot=user.username,
                provider=pod.cluster.rancher_provider,
                cluster=pod.cluster,
                mode=K8sAdminSession.MODE_BREAK_GLASS,
                status=K8sAdminSession.STATUS_ACTIVE,
                risk_tier=K8sAdminSession.RISK_CRITICAL,
                reason="live provider smoke node drain preflight proof",
                approval_ref="LIVE-SMOKE-DRAIN-PREFLIGHT",
                approved_by=user,
                approved_at=timezone.now(),
                allowed_verbs=["get", "list", "drain"],
                allowed_kinds=["node"],
                allowed_namespaces=["*"],
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            node_ref = KubernetesResourceRef(api_version="v1", kind="Node", resource="nodes", name=pod.node_name)
            node_path = rancher_resource_path(pod.cluster.rancher_provider, pod.cluster, node_ref)
            yaml_payload = get_cluster_resource_yaml(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{pod.cluster_id}",
                api_version="v1",
                kind="Pod",
                namespace=pod.namespace,
                name=pod.name,
            )
            log_payload = get_admin_pod_log_snapshot(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{pod.cluster_id}",
                namespace=pod.namespace,
                pod_name=pod.name,
                tail_lines=5,
            )
            describe_payload = get_cluster_resource_live_describe(
                user=user,
                session_id=str(session.session_id),
                cluster_id=f"cluster_{pod.cluster_id}",
                api_version="v1",
                kind="Pod",
                namespace=pod.namespace,
                name=pod.name,
                include_events=True,
                include_related=True,
                event_limit=5,
            )
            drain_preflight = build_node_drain_preflight(
                user=user,
                session=break_glass_session,
                cluster=pod.cluster,
                provider=pod.cluster.rancher_provider,
                ref=node_ref,
                path=node_path,
                reason="live provider smoke node drain preflight proof",
                confirmation=f"drain Node {pod.node_name}",
                options={"ignore_daemonsets": True, "delete_emptydir_data": False, "force": False, "max_pods": 100},
            )
            checks = [
                _backend_check(
                    "rancher_pod_yaml",
                    bool(yaml_payload.get("success")) and yaml_payload.get("operation") == "resource_yaml",
                    path=yaml_payload.get("path", ""),
                    source="admin_resource_yaml",
                    redacted=bool(yaml_payload.get("redacted")),
                ),
                _backend_check(
                    "rancher_pod_logs",
                    bool(log_payload.get("available")) and log_payload.get("source") == "provider_snapshot",
                    path=log_payload.get("path", ""),
                    source=log_payload.get("source", ""),
                    line_count=int(log_payload.get("line_count") or 0),
                    message=_redacted_text(log_payload.get("message")),
                ),
                _backend_check(
                    "rancher_pod_live_describe",
                    bool(describe_payload.get("success"))
                    and describe_payload.get("operation") == "resource_live_describe",
                    path=describe_payload.get("paths", {}).get("resource", ""),
                    source="admin_resource_live_describe",
                    event_count=int(describe_payload.get("events", {}).get("event_count") or 0),
                    related_pod_count=int(describe_payload.get("related", {}).get("pods", {}).get("item_count") or 0),
                    related_controller_count=int(
                        describe_payload.get("related", {}).get("controllers", {}).get("item_count") or 0
                    ),
                    redacted=bool(describe_payload.get("redacted")),
                ),
                _backend_check(
                    "rancher_node_drain_preflight",
                    drain_preflight.get("operation") == "node_drain_preflight"
                    and drain_preflight.get("status") == "planned"
                    and drain_preflight.get("drain_started") is False
                    and drain_preflight.get("evictions_started") is False,
                    path=drain_preflight.get("path", ""),
                    source="provider_node_drain_preflight",
                    pods_considered=int(drain_preflight.get("pods_considered") or 0),
                    blocked_reason=drain_preflight.get("blocked_reason", ""),
                    drain_started=bool(drain_preflight.get("drain_started")),
                    evictions_started=bool(drain_preflight.get("evictions_started")),
                ),
            ]
            success = all(item["success"] for item in checks)
            evidence = {
                "status": "ready" if success else "failed",
                "success": success,
                "mode": "transaction_rollback",
                "target": {
                    "cluster": pod.cluster.name,
                    "namespace": pod.namespace,
                    "pod": pod.name,
                    "node": pod.node_name,
                    "provider": pod.cluster.rancher_provider.name if pod.cluster.rancher_provider else "",
                },
                "checks": checks,
                "persistent_rows": False,
            }
            transaction.set_rollback(True)
            return evidence
    except Exception as exc:
        return {
            "status": "failed",
            "success": False,
            "reason": "backend path smoke failed",
            "target": {"cluster": pod.cluster.name, "namespace": pod.namespace, "pod": pod.name, "node": pod.node_name},
            "checks": [],
            "error": _redacted_text(exc),
        }


def _backend_path_target_pod() -> K8sPodRef | None:
    pods = (
        K8sPodRef.objects.select_related("cluster", "cluster__rancher_provider")
        .filter(
            cluster__rancher_provider__enabled=True,
            cluster__rancher_provider__kind=K8sProvider.KIND_RANCHER,
        )
        .exclude(namespace="")
        .exclude(name="")
        .exclude(node_name="")
    )
    return pods.filter(phase__iexact="Running").first() or pods.first()


def _backend_path_user():
    User = get_user_model()
    user = User.objects.create_user(
        username=f"k8s-live-provider-smoke-{uuid.uuid4().hex[:12]}", password="live-provider-smoke"
    )
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
    UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
    return user


def _backend_check(check_id: str, success: bool, **payload: Any) -> dict[str, Any]:
    return {"id": check_id, "success": bool(success), "status": "ready" if success else "failed", **payload}


def _provider_requirement_errors(
    providers: list[K8sProvider],
    *,
    require_rancher: bool,
    require_devtron: bool,
) -> list[str]:
    kinds = {provider.kind for provider in providers}
    errors: list[str] = []
    if require_rancher and K8sProvider.KIND_RANCHER not in kinds:
        errors.append("provider_missing:rancher")
    if require_devtron and K8sProvider.KIND_DEVTRON not in kinds:
        errors.append("provider_missing:devtron")
    return errors


def _provider_probe_errors(provider_probes: list[dict[str, Any]]) -> list[str]:
    return [
        f"provider_probe:{_safe_label(item.get('provider_name') or item.get('reason'))}={item.get('status') or 'failed'}"
        for item in provider_probes
        if not item.get("success")
    ]


def _sync_dry_run_errors(sync_dry_run: list[dict[str, Any]], *, require_fleet: bool) -> list[str]:
    errors: list[str] = []
    for item in sync_dry_run:
        if not item.get("success"):
            errors.append(f"sync_dry_run:{_safe_label(item.get('provider_name') or item.get('reason'))}=failed")
            continue
        provider_kind = str(item.get("provider_kind") or "")
        if provider_kind == K8sProvider.KIND_RANCHER:
            for field in RANCHER_REQUIRED_COUNTS:
                if _int(item.get(field)) <= 0:
                    errors.append(f"rancher_sync_empty:{_safe_label(item.get('provider_name'))}:{field}")
            if require_fleet and _int(item.get("fleet_bundles")) <= 0:
                errors.append(f"fleet_sync_empty:{_safe_label(item.get('provider_name'))}:fleet_bundles")
        if provider_kind == K8sProvider.KIND_DEVTRON:
            for field in DEVTRON_REQUIRED_COUNTS:
                if _int(item.get(field)) <= 0:
                    errors.append(f"devtron_sync_empty:{_safe_label(item.get('provider_name'))}:{field}")
    return errors


def _backend_path_errors(backend_paths: dict[str, Any], *, require_backend_paths: bool) -> list[str]:
    if not require_backend_paths:
        return []
    if backend_paths.get("success"):
        return []
    status = str(backend_paths.get("status") or "failed")
    errors = [f"backend_paths:{status}"]
    for item in backend_paths.get("checks") or []:
        if isinstance(item, dict) and not item.get("success"):
            errors.append(f"backend_path:{_safe_label(item.get('id'))}={_safe_label(item.get('status') or 'failed')}")
    return errors


def _summary(
    *,
    providers: list[K8sProvider],
    provider_probes: list[dict[str, Any]],
    sync_dry_run: list[dict[str, Any]],
    backend_paths: dict[str, Any],
) -> dict[str, Any]:
    rancher_sync = [
        item for item in sync_dry_run if item.get("provider_kind") == K8sProvider.KIND_RANCHER and item.get("success")
    ]
    devtron_sync = [
        item for item in sync_dry_run if item.get("provider_kind") == K8sProvider.KIND_DEVTRON and item.get("success")
    ]
    backend_checks = backend_paths.get("checks") if isinstance(backend_paths.get("checks"), list) else []
    return {
        "enabled_providers": len(providers),
        "rancher_providers": sum(1 for provider in providers if provider.kind == K8sProvider.KIND_RANCHER),
        "devtron_providers": sum(1 for provider in providers if provider.kind == K8sProvider.KIND_DEVTRON),
        "provider_probes_ok": sum(1 for item in provider_probes if item.get("success")),
        "provider_probes_total": len(provider_probes),
        "sync_dry_run_ok": sum(1 for item in sync_dry_run if item.get("success")),
        "sync_dry_run_total": len(sync_dry_run),
        "clusters": sum(_int(item.get("clusters")) for item in rancher_sync),
        "namespaces": sum(_int(item.get("namespaces")) for item in rancher_sync),
        "workloads": sum(_int(item.get("workloads")) for item in rancher_sync),
        "pods": sum(_int(item.get("pods")) for item in rancher_sync),
        "fleet_bundles": sum(_int(item.get("fleet_bundles")) for item in rancher_sync),
        "apps": sum(_int(item.get("apps")) for item in devtron_sync),
        "backend_paths_status": backend_paths.get("status", ""),
        "backend_path_checks_ok": sum(1 for item in backend_checks if item.get("success")),
        "backend_path_checks_total": len(backend_checks),
    }


def _public_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    netloc = _safe_netloc(parsed)
    if not netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme, netloc, "", "", ""))[:300]


def _public_path(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or ""))
    if not parsed.scheme and not parsed.netloc:
        return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:300]
    netloc = _safe_netloc(parsed)
    if not netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))[:300]


def _safe_netloc(parsed: urllib.parse.SplitResult) -> str:
    host = parsed.hostname or ""
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    return f"{host}:{port}" if port else host


def _redacted_text(value: object) -> str:
    return redact_egress_text(str(value or "")).text[:1000]


def _safe_label(value: object) -> str:
    label = _redacted_text(value).replace("\r", " ").replace("\n", " ").strip()
    return label[:120] or "unknown"


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
