from __future__ import annotations

import pytest

from kubernetes_ops.models import K8sAuditEvent, K8sCluster
from kubernetes_ops.services.release_audit_redaction import build_kubernetes_release_audit_redaction_evidence


@pytest.mark.django_db
def test_kubernetes_release_audit_redaction_is_rollback_only():
    before_events = K8sAuditEvent.objects.count()
    before_clusters = K8sCluster.objects.count()

    proof = build_kubernetes_release_audit_redaction_evidence()

    assert proof["status"] == "ready"
    assert proof["serializers_checked"] == ["serialize_audit_event", "serialize_cluster_event"]
    assert all(proof["checks"].values())
    assert K8sAuditEvent.objects.count() == before_events
    assert K8sCluster.objects.count() == before_clusters
    for raw in (
        "audit-redaction-token",
        "audit-redaction-password",
        "audit-redaction-url-token",
        "audit-redaction-url-password",
        "audit.redaction.jwt",
    ):
        assert raw not in str(proof)
