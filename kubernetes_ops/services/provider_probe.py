from __future__ import annotations

import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.normalizers import payload_items
from kubernetes_ops.services.provider_clients import DevtronClient, ProviderJsonClient, ProviderTransport, provider_path
from kubernetes_ops.services.secrets import redact_secret, resolve_provider_token


@dataclass(frozen=True)
class KubernetesProviderProbeResult:
    provider_id: int
    provider_name: str
    provider_kind: str
    success: bool
    status: str
    path: str
    item_count: int = 0
    payload_keys: tuple[str, ...] = ()
    duration_ms: int = 0
    checked_at: str = ""
    error: str = ""


def probe_kubernetes_provider(
    provider: K8sProvider,
    *,
    transport: ProviderTransport | None = None,
) -> KubernetesProviderProbeResult:
    token = ""
    path = _probe_path(provider)
    started = time.perf_counter()
    try:
        token = resolve_provider_token(provider)
        if provider.kind == K8sProvider.KIND_DEVTRON:
            payload = DevtronClient(provider, transport=transport).get(path)
        else:
            payload = ProviderJsonClient(provider, transport=transport).get(path)
        duration_ms = int((time.perf_counter() - started) * 1000)
        items = payload_items(payload)
        return KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=True,
            status="ready",
            path=_public_path(path),
            item_count=len(items),
            payload_keys=_payload_keys(payload),
            duration_ms=duration_ms,
            checked_at=timezone.now().isoformat(),
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return KubernetesProviderProbeResult(
            provider_id=provider.id,
            provider_name=provider.name,
            provider_kind=provider.kind,
            success=False,
            status="error",
            path=_public_path(path),
            duration_ms=duration_ms,
            checked_at=timezone.now().isoformat(),
            error=redact_secret(exc, token),
        )


def probe_result_payload(result: KubernetesProviderProbeResult) -> dict[str, Any]:
    return {
        "provider_id": result.provider_id,
        "provider_name": result.provider_name,
        "provider_kind": result.provider_kind,
        "success": result.success,
        "status": result.status,
        "path": result.path,
        "item_count": result.item_count,
        "payload_keys": list(result.payload_keys),
        "duration_ms": result.duration_ms,
        "checked_at": result.checked_at,
        "error": result.error,
    }


def _probe_path(provider: K8sProvider) -> str:
    explicit = provider_path(provider, "probe_path", "").strip()
    if explicit:
        return explicit
    if provider.kind == K8sProvider.KIND_DEVTRON:
        return provider_path(provider, "apps_path", "/orchestrator/app/list")
    return provider_path(provider, "clusters_path", "/v3/clusters")


def _public_path(path: str) -> str:
    parsed = urllib.parse.urlsplit(str(path or ""))
    if not parsed.scheme and not parsed.netloc:
        return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:300]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))[:300]


def _payload_keys(payload: dict[str, Any]) -> tuple[str, ...]:
    keys: list[str] = []
    for key in payload:
        normalized = str(key)
        if any(part in normalized.lower() for part in ("token", "secret", "password", "authorization", "credential")):
            keys.append("[redacted]")
        else:
            keys.append(normalized[:80])
    return tuple(sorted(keys)[:12])
