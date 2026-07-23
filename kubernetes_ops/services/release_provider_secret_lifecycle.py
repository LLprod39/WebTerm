from __future__ import annotations

import uuid
from typing import Any

from app.egress_redaction import redact_egress_text
from core_ui.managed_secrets import (
    KUBERNETES_PROVIDER_TOKEN_NAMESPACE,
    delete_kubernetes_provider_token,
    get_kubernetes_provider_token,
    has_kubernetes_provider_token,
    set_kubernetes_provider_token,
)
from core_ui.models import ManagedSecret
from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.secrets import managed_provider_secret_ref


def build_kubernetes_release_provider_secret_lifecycle_evidence(enabled: bool = True) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "provider secret lifecycle proof skipped"}

    provider_id: int | None = None
    initial_value = f"webterm-provider-initial-{uuid.uuid4()}"
    rotated_value = f"webterm-provider-rotated-{uuid.uuid4()}"
    checks: dict[str, bool] = {}

    try:
        provider = K8sProvider.objects.create(
            name=f"release-secret-proof-{uuid.uuid4().hex[:12]}",
            kind=K8sProvider.KIND_RANCHER,
            base_url="https://rotation-proof.invalid",
            auth_mode=K8sProvider.AUTH_SECRET_REF,
        )
        provider_id = int(provider.id)

        set_kubernetes_provider_token(provider_id, initial_value)
        provider.secret_ref = managed_provider_secret_ref(provider_id)
        provider.save(update_fields=["secret_ref", "updated_at"])
        first_row = _managed_row(provider_id)
        first_ciphertext = first_row.ciphertext if first_row else ""

        checks["managed_storage_created"] = bool(first_row) and has_kubernetes_provider_token(provider_id)
        checks["managed_ref_bound_to_provider"] = provider.secret_ref == managed_provider_secret_ref(provider_id)
        checks["initial_value_resolved"] = get_kubernetes_provider_token(provider_id) == initial_value
        checks["initial_plaintext_not_in_ciphertext"] = initial_value not in first_ciphertext

        set_kubernetes_provider_token(provider_id, rotated_value)
        rotated_row = _managed_row(provider_id)
        rotated_ciphertext = rotated_row.ciphertext if rotated_row else ""

        checks["rotation_value_resolved"] = get_kubernetes_provider_token(provider_id) == rotated_value
        checks["rotation_reencrypted_payload"] = bool(rotated_ciphertext) and rotated_ciphertext != first_ciphertext
        checks["rotated_plaintext_not_in_ciphertext"] = rotated_value not in rotated_ciphertext
    except Exception as exc:
        return {
            "success": False,
            "status": "error",
            "mode": "rollback",
            "error": redact_egress_text(str(exc)).text[:500],
            "checks": checks,
        }
    finally:
        if provider_id is not None:
            delete_kubernetes_provider_token(provider_id)
            K8sProvider.objects.filter(id=provider_id).delete()

    if provider_id is not None:
        checks["rollback_removed_provider"] = not K8sProvider.objects.filter(id=provider_id).exists()
        checks["rollback_removed_managed_storage"] = not ManagedSecret.objects.filter(
            namespace=KUBERNETES_PROVIDER_TOKEN_NAMESPACE,
            object_id=provider_id,
        ).exists()

    payload = {
        "success": False,
        "status": "missing",
        "mode": "rollback",
        "storage_mode": "managed",
        "rotation_supported": bool(checks.get("rotation_value_resolved")),
        "persistent_rows": not bool(
            checks.get("rollback_removed_provider") and checks.get("rollback_removed_managed_storage")
        ),
        "checks": checks,
    }
    checks["plaintext_not_serialized"] = initial_value not in str(payload) and rotated_value not in str(payload)
    success = all(checks.values()) if checks else False
    payload["success"] = success
    payload["status"] = "ready" if success else "failed"
    payload["rotation_supported"] = bool(checks.get("rotation_value_resolved"))
    payload["persistent_rows"] = not bool(
        checks.get("rollback_removed_provider") and checks.get("rollback_removed_managed_storage")
    )
    return payload


def provider_secret_lifecycle_blocker(evidence: dict[str, Any]) -> str:
    if evidence.get("success"):
        return ""
    return f"provider_secret_lifecycle:{evidence.get('status') or 'failed'}"


def _managed_row(provider_id: int) -> ManagedSecret | None:
    return ManagedSecret.objects.filter(
        namespace=KUBERNETES_PROVIDER_TOKEN_NAMESPACE,
        object_id=provider_id,
    ).first()
