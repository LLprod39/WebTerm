from __future__ import annotations

from typing import Any

from app.egress_redaction import redact_egress_text
from kubernetes_ops.models import K8sAuditEvent, K8sCluster
from kubernetes_ops.serializers import serialize_audit_event, serialize_cluster_event

RAW_MARKERS = (
    "audit-redaction-token",
    "audit-redaction-password",
    "audit-redaction-url-token",
    "audit-redaction-url-password",
    "audit.redaction.jwt",
)


def build_kubernetes_release_audit_redaction_evidence(enabled: bool = True) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "audit redaction proof skipped"}

    cluster_id: int | None = None
    event_id: int | None = None
    checks: dict[str, bool] = {}

    try:
        cluster = K8sCluster.objects.create(name="release-audit-redaction-proof")
        cluster_id = int(cluster.id)
        event = K8sAuditEvent.objects.create(
            action="k8s.release.audit_redaction.proof",
            provider="webterm",
            cluster=cluster,
            payload={
                "target_name": "redaction-proof",
                "token": "audit-redaction-token",
                "message": "password=audit-redaction-password\nAuthorization: Bearer audit.redaction.jwt",
                "url": "https://user:audit-redaction-url-password@rancher.redaction-proof.invalid/path?token=audit-redaction-url-token#tail",
                "nested": {
                    "dsn": "postgres://audit:audit-redaction-password@db.redaction-proof.invalid:5432/app",
                    "notes": ["api_key=audit-redaction-token"],
                },
            },
        )
        event_id = int(event.id)

        api_payload = serialize_audit_event(event)
        cluster_payload = serialize_cluster_event(event)
        serialized_api = str(api_payload)
        serialized_cluster = str(cluster_payload)

        checks["audit_event_created"] = True
        checks["api_serializer_raw_values_absent"] = _raw_absent(serialized_api)
        checks["cluster_event_raw_values_absent"] = _raw_absent(serialized_cluster)
        checks["sensitive_key_redacted"] = api_payload.get("payload", {}).get("token") == "[redacted]"
        checks["credentialed_url_sanitized"] = api_payload.get("payload", {}).get("url") == "https://rancher.redaction-proof.invalid/path"
        checks["connection_string_redacted"] = "[REDACTED:connection_string]" in serialized_api
        checks["bearer_redacted"] = "audit.redaction.jwt" not in serialized_api
    except Exception as exc:
        return {
            "success": False,
            "status": "error",
            "mode": "rollback",
            "error": redact_egress_text(str(exc)).text[:500],
            "checks": checks,
        }
    finally:
        if event_id is not None:
            K8sAuditEvent.objects.filter(id=event_id).delete()
        if cluster_id is not None:
            K8sCluster.objects.filter(id=cluster_id).delete()

    if event_id is not None:
        checks["rollback_removed_audit_event"] = not K8sAuditEvent.objects.filter(id=event_id).exists()
    if cluster_id is not None:
        checks["rollback_removed_cluster"] = not K8sCluster.objects.filter(id=cluster_id).exists()

    payload = {
        "success": False,
        "status": "missing",
        "mode": "rollback",
        "serializers_checked": ["serialize_audit_event", "serialize_cluster_event"],
        "checks": checks,
    }
    checks["proof_payload_raw_values_absent"] = _raw_absent(str(payload))
    success = all(checks.values()) if checks else False
    payload["success"] = success
    payload["status"] = "ready" if success else "failed"
    return payload


def audit_redaction_blocker(evidence: dict[str, Any]) -> str:
    if evidence.get("success"):
        return ""
    return f"audit_redaction:{evidence.get('status') or 'failed'}"


def _raw_absent(value: str) -> bool:
    text = str(value or "")
    return all(marker not in text for marker in RAW_MARKERS)
