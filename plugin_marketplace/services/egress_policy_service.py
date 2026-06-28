from __future__ import annotations

from typing import Any, Iterable

from django.conf import settings


def normalize_egress_host(value: Any) -> str:
    return str(value or "").strip().strip(".").lower()


def configured_denied_egress_hosts() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_EGRESS_DENIED_HOSTS", []) or []
    return {host for host in (normalize_egress_host(item) for item in configured) if host}


def manifest_egress_hosts(manifest: dict[str, Any]) -> set[str]:
    hosts: set[str] = set()
    egress = manifest.get("egress") if isinstance(manifest.get("egress"), list) else []
    for item in egress:
        if not isinstance(item, dict):
            continue
        host = normalize_egress_host(item.get("host"))
        if host:
            hosts.add(host)
        for field in ("hosts", "hostnames"):
            values = item.get(field) if isinstance(item.get(field), list) else []
            for value in values:
                normalized = normalize_egress_host(value)
                if normalized:
                    hosts.add(normalized)
    return hosts


def denied_egress_hosts(hosts: Iterable[str]) -> list[str]:
    denied = configured_denied_egress_hosts()
    return sorted({host for host in (normalize_egress_host(item) for item in hosts) if host in denied})


def egress_policy_blockers(manifest: dict[str, Any]) -> list[str]:
    return [f"Egress host denied by policy: {host}." for host in denied_egress_hosts(manifest_egress_hosts(manifest))]
