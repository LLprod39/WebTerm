from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAppRef, K8sCluster
from kubernetes_ops.services.release_studio_diagnosis import build_kubernetes_release_studio_diagnosis_draft_evidence
from studio.models import MCPServerPool, Pipeline, PipelineDraftSession, PipelineRun


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": True})


@pytest.mark.django_db
def test_studio_diagnosis_draft_release_proof_is_read_only_and_rolled_back():
    user = User.objects.create_user(username="release-studio-proof", password="x", is_staff=True)
    _grant(user, "kubernetes", "studio_pipelines", "studio_mcp")
    MCPServerPool.objects.create(
        name="Kubernetes MCP",
        description="kubectl read-only diagnostics",
        transport=MCPServerPool.TRANSPORT_STDIO,
        command="npx",
        args=["-y", "@modelcontextprotocol/server-kubernetes"],
        owner=user,
        last_test_ok=True,
    )
    cluster = K8sCluster.objects.create(name="prod-kz-1", environment="prod", labels={"kube_context": "prod-kz"})
    K8sAppRef.objects.create(
        name="payments-api",
        cluster=cluster,
        namespace="payments",
        environment="prod",
        owner=K8sAppRef.OWNER_DEVTRON,
        team="payments",
        labels={"workload_kind": "statefulset"},
    )

    before = {
        "drafts": PipelineDraftSession.objects.count(),
        "pipelines": Pipeline.objects.count(),
        "runs": PipelineRun.objects.count(),
    }

    proof = build_kubernetes_release_studio_diagnosis_draft_evidence(user, True)

    assert proof["success"] is True
    assert proof["status"] == "ready"
    assert proof["mode"] == "transaction_rollback"
    assert proof["draft_status"] == PipelineDraftSession.STATUS_READY
    assert proof["draft_rows_created"] == 1
    assert proof["pipeline_rows_created"] == 0
    assert proof["pipeline_run_rows_created"] == 0
    assert proof["inspect_tool"] == "kubernetes_describe_workload"
    assert proof["permission_mode"] == "READ_ONLY"
    assert proof["mutates_state"] is False
    assert proof["operation_kind"] == "kubernetes.workload.describe"
    assert proof["skill_slugs"] == ["kubernetes-safety"]
    assert proof["forbidden_tools"] == []
    assert proof["validation_ok"] is True
    assert proof["persistent_rows"] is False
    assert PipelineDraftSession.objects.count() == before["drafts"]
    assert Pipeline.objects.count() == before["pipelines"]
    assert PipelineRun.objects.count() == before["runs"]
