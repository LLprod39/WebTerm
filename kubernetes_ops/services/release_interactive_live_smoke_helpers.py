from __future__ import annotations

from datetime import UTC
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

INTERACTIVE_LIVE_SMOKE_SCHEMA_VERSION = "kubernetes_ops.interactive_live_smoke.v1"
INTERACTIVE_LIVE_SMOKE_ARTIFACT = "artifacts/kubernetes_ops_interactive_live_smoke.json"
INTERACTIVE_LIVE_SMOKE_EVIDENCE_SETTING = "KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF"
INTERACTIVE_LIVE_SMOKE_REQUIRED_SETTING = "KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_REQUIRED"
LIVE_TRANSPORT_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "transport": "exec_stream",
        "simulated_check_id": "provider_exec_stream_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "recording_enabled",
            "break_glass_session_ttl",
            "command_policy",
            "provider_exec_opener",
        ),
    },
    {
        "transport": "port_forward_tunnel",
        "simulated_check_id": "provider_port_forward_tunnel_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "network_policy_ref",
            "exact_target_allowlist",
            "ttl_cap",
            "provider_tunnel_opener",
        ),
    },
    {
        "transport": "cluster_terminal",
        "simulated_check_id": "provider_cluster_terminal_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "recording_enabled",
            "provider_path_template",
            "break_glass_session_ttl",
            "provider_shell_opener",
        ),
    },
    {
        "transport": "node_debug",
        "simulated_check_id": "provider_node_debug_opener",
        "production_evidence_required": (
            "restricted_credential_ref",
            "recording_enabled",
            "provider_path_template",
            "node_scope",
            "provider_shell_opener",
        ),
    },
)


def _capture_transport(payload: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def transport(url, _headers, _timeout, *, method="GET", body=None):
        captured.update({"url": str(url), "method": str(method).upper(), "body": dict(body or {})})
        return payload

    return {"transport": transport, "captured": captured}


def _request_summary(captured: dict[str, Any], *, operation: str) -> dict[str, Any]:
    raw = captured.get("captured") if isinstance(captured.get("captured"), dict) else {}
    body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
    target = body.get("target") if isinstance(body.get("target"), dict) else {}
    return {
        "operation": str(body.get("operation") or operation),
        "method": str(raw.get("method") or ""),
        "body_keys": sorted(body.keys()),
        "target_keys": sorted(target.keys()),
        "stdin": bool(body.get("stdin")),
        "tty": bool(body.get("tty")),
        "duration_seconds": int(body.get("duration_seconds") or 0),
    }


def _request_safe(request: dict[str, Any]) -> bool:
    serialized = str(request)
    forbidden = ("smoke-secret", "stdin-secret", "Authorization:", "Bearer ")
    return not any(item in serialized for item in forbidden)


def _live_smoke_required(*, production: bool, enabled_count: int) -> bool:
    configured = bool(getattr(settings, INTERACTIVE_LIVE_SMOKE_REQUIRED_SETTING, False))
    return configured or bool(production and enabled_count > 0)


def _setting_ref(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _artifact_age(payload: dict[str, Any]) -> tuple[int | None, str]:
    raw = str(payload.get("checked_at") or "").strip()
    if not raw:
        return None, "checked_at is missing"
    checked_at = parse_datetime(raw)
    if checked_at is None:
        return None, "checked_at is invalid"
    if timezone.is_naive(checked_at):
        checked_at = timezone.make_aware(checked_at, timezone=UTC)
    age_seconds = max(0, int((timezone.now() - checked_at).total_seconds()))
    max_age_seconds = _max_age_seconds()
    if age_seconds > max_age_seconds:
        return (
            age_seconds,
            f"interactive live-smoke artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return age_seconds, ""


def _max_age_seconds() -> int:
    return int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
