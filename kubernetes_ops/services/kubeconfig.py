"""Parse, probe, and inventory sync for personal/platform kubeconfig connections."""

from __future__ import annotations

import base64
import json
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from django.db import transaction
from django.utils import timezone

from kubernetes_ops.models import K8sCluster, K8sNamespace, K8sPodRef, K8sProvider
from kubernetes_ops.services.secrets import redact_secret, resolve_provider_token

MAX_KUBECONFIG_BYTES = 256 * 1024
_CLUSTER_NAME_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class KubeconfigContextInfo:
    name: str
    cluster_name: str
    user_name: str
    server: str
    namespace: str = ""


@dataclass(frozen=True)
class KubeconfigParseResult:
    contexts: list[KubeconfigContextInfo]
    current_context: str
    document: dict[str, Any]


@dataclass
class KubeconfigProbeResult:
    success: bool
    status: str
    server: str = ""
    context: str = ""
    namespace_count: int = 0
    duration_ms: int = 0
    error: str = ""
    checked_at: str = ""


def parse_kubeconfig_text(raw: str) -> KubeconfigParseResult:
    text = str(raw or "")
    if not text.strip():
        raise ValueError("kubeconfig is empty.")
    if len(text.encode("utf-8")) > MAX_KUBECONFIG_BYTES:
        raise ValueError(f"kubeconfig exceeds {MAX_KUBECONFIG_BYTES} bytes.")
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid kubeconfig YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("kubeconfig must be a YAML object.")

    clusters_by_name = {
        str(item.get("name") or "").strip(): item.get("cluster") or {}
        for item in (document.get("clusters") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    users_by_name = {
        str(item.get("name") or "").strip(): True
        for item in (document.get("users") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }

    contexts: list[KubeconfigContextInfo] = []
    for item in document.get("contexts") or []:
        if not isinstance(item, dict):
            continue
        ctx_name = str(item.get("name") or "").strip()
        ctx = item.get("context") or {}
        if not ctx_name or not isinstance(ctx, dict):
            continue
        cluster_name = str(ctx.get("cluster") or "").strip()
        user_name = str(ctx.get("user") or "").strip()
        cluster = clusters_by_name.get(cluster_name) or {}
        server = str(cluster.get("server") or "").strip().rstrip("/")
        if not server.startswith(("https://", "http://")):
            continue
        if user_name and user_name not in users_by_name:
            continue
        contexts.append(
            KubeconfigContextInfo(
                name=ctx_name,
                cluster_name=cluster_name,
                user_name=user_name,
                server=server,
                namespace=str(ctx.get("namespace") or "").strip(),
            )
        )

    if not contexts:
        raise ValueError("kubeconfig has no usable contexts with a cluster server URL.")

    current = str(document.get("current-context") or "").strip()
    names = {item.name for item in contexts}
    if current not in names:
        current = contexts[0].name

    return KubeconfigParseResult(contexts=contexts, current_context=current, document=document)


def select_context(parsed: KubeconfigParseResult, context_name: str = "") -> KubeconfigContextInfo:
    wanted = str(context_name or "").strip() or parsed.current_context
    for item in parsed.contexts:
        if item.name == wanted:
            return item
    raise ValueError(f"Context '{wanted}' not found in kubeconfig.")


def provider_scope_for_user(*, is_staff: bool, requested: str = "") -> str:
    value = str(requested or "").strip().lower()
    if value == K8sProvider.SCOPE_PLATFORM:
        if not is_staff:
            raise ValueError("Platform kubeconfig connections are admin-only.")
        return K8sProvider.SCOPE_PLATFORM
    return K8sProvider.SCOPE_PERSONAL


def connection_external_id(provider_id: int) -> str:
    return f"kubeconfig:{provider_id}"


def connection_cluster_name(provider: K8sProvider, context: KubeconfigContextInfo) -> str:
    labels = provider.labels if isinstance(provider.labels, dict) else {}
    explicit = str(labels.get("cluster_display_name") or "").strip()
    raw = explicit or f"{provider.name}-{context.name}"
    cleaned = _CLUSTER_NAME_SAFE.sub("-", raw).strip("-._")[:140]
    return cleaned or f"kubeconfig-{provider.id}"


def materialize_connection_cluster(provider: K8sProvider, context: KubeconfigContextInfo) -> K8sCluster:
    labels = dict(provider.labels) if isinstance(provider.labels, dict) else {}
    labels.update(
        {
            "source": "kubeconfig",
            "provider_id": provider.id,
            "context": context.name,
            "scope": provider.scope,
            "server": context.server,
        }
    )
    desired_name = connection_cluster_name(provider, context)
    external_id = connection_external_id(provider.id)
    cluster = K8sCluster.objects.filter(rancher_cluster_id=external_id).first()
    if cluster is None:
        # Avoid unique-name collision with unrelated inventory rows.
        name = desired_name
        if K8sCluster.objects.filter(name=name).exists():
            name = f"{desired_name}-{provider.id}"
        cluster = K8sCluster.objects.create(
            name=name,
            environment=(
                "personal" if provider.scope == K8sProvider.SCOPE_PERSONAL else "platform"
            ),
            health=K8sCluster.HEALTH_UNKNOWN,
            rancher_provider=None,
            rancher_cluster_id=external_id,
            labels=labels,
            links={"api_server": context.server},
        )
        return cluster

    cluster.environment = "personal" if provider.scope == K8sProvider.SCOPE_PERSONAL else "platform"
    cluster.labels = labels
    cluster.links = {"api_server": context.server}
    if cluster.name != desired_name and not K8sCluster.objects.filter(name=desired_name).exclude(id=cluster.id).exists():
        cluster.name = desired_name
    cluster.save(update_fields=["environment", "labels", "links", "name", "updated_at"])
    return cluster


def probe_kubeconfig_provider(provider: K8sProvider) -> KubeconfigProbeResult:
    started = time.perf_counter()
    raw = ""
    try:
        raw = resolve_provider_token(provider)
        parsed = parse_kubeconfig_text(raw)
        labels = provider.labels if isinstance(provider.labels, dict) else {}
        context = select_context(parsed, str(labels.get("context") or ""))
        namespaces = _list_namespaces(raw, context.name)
        return KubeconfigProbeResult(
            success=True,
            status="ready",
            server=context.server,
            context=context.name,
            namespace_count=len(namespaces),
            duration_ms=int((time.perf_counter() - started) * 1000),
            checked_at=timezone.now().isoformat(),
        )
    except Exception as exc:
        return KubeconfigProbeResult(
            success=False,
            status="error",
            duration_ms=int((time.perf_counter() - started) * 1000),
            checked_at=timezone.now().isoformat(),
            error=redact_secret(exc, raw),
        )


def sync_kubeconfig_provider(provider: K8sProvider, *, dry_run: bool = False):
    from kubernetes_ops.services.sync import KubernetesSyncResult

    result = KubernetesSyncResult(
        provider_id=provider.id,
        provider_name=provider.name,
        provider_kind=provider.kind,
        success=False,
        dry_run=dry_run,
    )
    raw = ""
    try:
        raw = resolve_provider_token(provider)
        parsed = parse_kubeconfig_text(raw)
        labels = provider.labels if isinstance(provider.labels, dict) else {}
        context = select_context(parsed, str(labels.get("context") or ""))
        namespaces = _list_namespaces(raw, context.name)
        pods = _list_pods(raw, context.name) if not dry_run else []
        if dry_run:
            result.success = True
            result.clusters = 1
            result.namespaces = len(namespaces)
            return result

        keep_ns: list[str] = []
        keep_pods: list[tuple[str, str]] = []
        with transaction.atomic():
            cluster = materialize_connection_cluster(provider, context)
            for item in namespaces:
                ns_name = str((item.get("metadata") or {}).get("name") or "").strip()
                if not ns_name:
                    continue
                keep_ns.append(ns_name)
                K8sNamespace.objects.update_or_create(
                    cluster=cluster,
                    name=ns_name,
                    defaults={
                        "environment": cluster.environment,
                        "health": K8sCluster.HEALTH_HEALTHY,
                        "last_sync_at": timezone.now(),
                    },
                )
            if keep_ns:
                K8sNamespace.objects.filter(cluster=cluster).exclude(name__in=keep_ns).delete()

            for item in pods:
                meta = item.get("metadata") or {}
                status = item.get("status") or {}
                spec = item.get("spec") or {}
                ns = str(meta.get("namespace") or "").strip()
                name = str(meta.get("name") or "").strip()
                if not ns or not name:
                    continue
                keep_pods.append((ns, name))
                ready_n, total_n = _pod_container_counts(status)
                phase = str(status.get("phase") or "Unknown")
                health = (
                    K8sCluster.HEALTH_HEALTHY
                    if phase.lower() == "running" and ready_n == total_n and total_n > 0
                    else K8sCluster.HEALTH_WARNING
                    if phase.lower() in {"pending", "unknown"}
                    else K8sCluster.HEALTH_DEGRADED
                )
                K8sPodRef.objects.update_or_create(
                    cluster=cluster,
                    namespace=ns,
                    name=name,
                    defaults={
                        "environment": cluster.environment,
                        "health": health,
                        "phase": phase,
                        "node_name": str(spec.get("nodeName") or ""),
                        "pod_ip": str(status.get("podIP") or ""),
                        "host_ip": str(status.get("hostIP") or ""),
                        "ready_containers": ready_n,
                        "total_containers": total_n,
                        "restart_count": _pod_restarts(status),
                        "labels": dict(meta.get("labels") or {}),
                        "last_sync_at": timezone.now(),
                    },
                )
            if keep_pods:
                for pod in list(K8sPodRef.objects.filter(cluster=cluster)):
                    if (pod.namespace, pod.name) not in keep_pods:
                        pod.delete()
            else:
                K8sPodRef.objects.filter(cluster=cluster).delete()

            cluster.namespace_count = len(keep_ns)
            cluster.workload_count = len(keep_pods)
            cluster.health = K8sCluster.HEALTH_HEALTHY
            cluster.last_sync_at = timezone.now()
            cluster.save(
                update_fields=[
                    "namespace_count",
                    "workload_count",
                    "health",
                    "last_sync_at",
                    "labels",
                    "links",
                    "updated_at",
                ]
            )
            provider.last_sync_at = timezone.now()
            provider.last_error = ""
            provider.base_url = context.server
            provider.save(update_fields=["last_sync_at", "last_error", "base_url", "updated_at"])

        result.success = True
        result.clusters = 1
        result.namespaces = len(keep_ns)
        result.pods = len(keep_pods)
        return result
    except Exception as exc:
        provider.last_error = redact_secret(exc, raw)
        provider.save(update_fields=["last_error", "updated_at"])
        result.error = provider.last_error
        return result


def _b64_to_temp_pem(data_b64: str, *, prefix: str) -> Path:
    raw = base64.b64decode(str(data_b64 or "").strip())
    path = Path(tempfile.mkstemp(prefix=prefix, suffix=".pem")[1])
    if raw.lstrip().startswith(b"-----"):
        path.write_bytes(raw)
    else:
        # DER → PEM wrap is uncommon in kubeconfig (usually already PEM base64); write raw DER bytes.
        path.write_bytes(raw)
    return path


def _auth_headers_and_ssl(raw: str, context_name: str) -> tuple[str, dict[str, str], ssl.SSLContext]:
    parsed = parse_kubeconfig_text(raw)
    context = select_context(parsed, context_name)
    clusters = {
        str(i.get("name")): i.get("cluster") or {}
        for i in (parsed.document.get("clusters") or [])
        if isinstance(i, dict)
    }
    users = {
        str(i.get("name")): i.get("user") or {}
        for i in (parsed.document.get("users") or [])
        if isinstance(i, dict)
    }
    cluster = clusters.get(context.cluster_name) or {}
    user = users.get(context.user_name) or {}

    headers: dict[str, str] = {"Accept": "application/json"}
    token = str(user.get("token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if cluster.get("insecure-skip-tls-verify"):
        ssl_ctx = ssl._create_unverified_context()
    else:
        ssl_ctx = ssl.create_default_context()
        ca_data = str(cluster.get("certificate-authority-data") or "").strip()
        ca_file = str(cluster.get("certificate-authority") or "").strip()
        if ca_data:
            ca_path = _b64_to_temp_pem(ca_data, prefix="wt-ca-")
            ssl_ctx.load_verify_locations(cafile=str(ca_path))
        elif ca_file:
            ssl_ctx.load_verify_locations(cafile=ca_file)

    cert_data = str(user.get("client-certificate-data") or "").strip()
    key_data = str(user.get("client-key-data") or "").strip()
    cert_file = str(user.get("client-certificate") or "").strip()
    key_file = str(user.get("client-key") or "").strip()
    if cert_data and key_data:
        cert_path = _b64_to_temp_pem(cert_data, prefix="wt-cert-")
        key_path = _b64_to_temp_pem(key_data, prefix="wt-key-")
        ssl_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    elif cert_file and key_file:
        ssl_ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

    if not token and not ((cert_data and key_data) or (cert_file and key_file)):
        raise ValueError("kubeconfig user must provide token or client certificate credentials.")

    return context.server, headers, ssl_ctx


def _api_get(raw: str, context_name: str, path: str) -> dict[str, Any]:
    server, headers, ssl_ctx = _auth_headers_and_ssl(raw, context_name)
    url = server.rstrip("/") + "/" + path.lstrip("/")
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, context=ssl_ctx, timeout=20) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise ValueError(f"Kubernetes API {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Cannot reach Kubernetes API: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Kubernetes API returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Kubernetes API returned a non-object payload.")
    return payload


def _list_namespaces(raw: str, context_name: str) -> list[dict[str, Any]]:
    payload = _api_get(raw, context_name, "/api/v1/namespaces")
    return [item for item in (payload.get("items") or []) if isinstance(item, dict)]


def _list_pods(raw: str, context_name: str) -> list[dict[str, Any]]:
    payload = _api_get(raw, context_name, "/api/v1/pods")
    return [item for item in (payload.get("items") or []) if isinstance(item, dict)]


def _pod_container_counts(status: dict[str, Any]) -> tuple[int, int]:
    statuses = [cs for cs in (status.get("containerStatuses") or []) if isinstance(cs, dict)]
    total = len(statuses)
    ready = sum(1 for cs in statuses if cs.get("ready"))
    return ready, total


def _pod_restarts(status: dict[str, Any]) -> int:
    total = 0
    for cs in status.get("containerStatuses") or []:
        if isinstance(cs, dict):
            try:
                total += int(cs.get("restartCount") or 0)
            except (TypeError, ValueError):
                continue
    return total
