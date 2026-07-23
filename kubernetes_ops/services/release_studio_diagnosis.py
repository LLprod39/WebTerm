from __future__ import annotations

from typing import Any

from django.db import transaction

from kubernetes_ops.models import K8sAppRef
from kubernetes_ops.studio_drafts import create_kubernetes_diagnosis_draft
from studio.models import Pipeline, PipelineDraftSession, PipelineRun

_FORBIDDEN_TOOLS = {
    "kubernetes_rollout_restart",
    "kubernetes_rollout_status",
    "kubectl_apply",
    "kubectl_exec",
    "kubectl_delete",
    "kubernetes_scale_workload",
}


def build_kubernetes_release_studio_diagnosis_draft_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "studio diagnosis draft proof skipped"}
    if not user:
        return {
            "success": False,
            "status": "missing",
            "reason": "staff user is required for Studio diagnosis draft proof",
        }
    app = K8sAppRef.objects.select_related("cluster").order_by("id").first()
    if app is None:
        return {"success": False, "status": "missing", "reason": "no Kubernetes app target for diagnosis draft proof"}

    try:
        with transaction.atomic():
            before = _studio_counts()
            session = create_kubernetes_diagnosis_draft(user=user, app=app)
            latest = session.latest_revision()
            nodes = latest.preview_nodes if latest else []
            inspect_node = next((node for node in nodes if node.get("id") == "inspect"), {})
            inspect_data = inspect_node.get("data") if isinstance(inspect_node.get("data"), dict) else {}
            after = _studio_counts()
            errors = _diagnosis_draft_errors(
                session=session,
                latest=latest,
                inspect_data=inspect_data,
                nodes=nodes,
                before=before,
                after=after,
            )
            proof = {
                "success": not errors,
                "status": "ready" if not errors else "failed",
                "mode": "transaction_rollback",
                "draft_status": session.status,
                "draft_rows_created": after["drafts"] - before["drafts"],
                "pipeline_rows_created": after["pipelines"] - before["pipelines"],
                "pipeline_run_rows_created": after["runs"] - before["runs"],
                "inspect_tool": str(inspect_data.get("tool_name") or ""),
                "permission_mode": str(inspect_data.get("permission_mode") or ""),
                "mutates_state": bool(inspect_data.get("mutates_state")),
                "operation_kind": str(inspect_data.get("operation_kind") or ""),
                "skill_slugs": list(inspect_data.get("skill_slugs") or []),
                "forbidden_tools": sorted(_node_tool_names(nodes) & _FORBIDDEN_TOOLS),
                "validation_ok": bool((latest.validation if latest else {}).get("ok")),
                "persistent_rows": False,
                "errors": errors,
            }
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def _studio_counts() -> dict[str, int]:
    return {
        "drafts": PipelineDraftSession.objects.count(),
        "pipelines": Pipeline.objects.count(),
        "runs": PipelineRun.objects.count(),
    }


def _node_tool_names(nodes: list[dict[str, Any]]) -> set[str]:
    return {
        str((node.get("data") if isinstance(node.get("data"), dict) else {}).get("tool_name") or "")
        for node in nodes
        if isinstance(node, dict)
    }


def _diagnosis_draft_errors(
    *,
    session: PipelineDraftSession,
    latest,
    inspect_data: dict[str, Any],
    nodes: list[dict[str, Any]],
    before: dict[str, int],
    after: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    if session.status != PipelineDraftSession.STATUS_READY:
        errors.append(f"draft status is {session.status}")
    if latest is None:
        errors.append("draft revision is missing")
        return errors
    if not latest.validation.get("ok"):
        errors.append("draft validation is not ok")
    if after["drafts"] != before["drafts"] + 1:
        errors.append("draft row was not created")
    if after["pipelines"] != before["pipelines"]:
        errors.append("pipeline row was created")
    if after["runs"] != before["runs"]:
        errors.append("pipeline run row was created")
    if inspect_data.get("tool_name") != "kubernetes_describe_workload":
        errors.append("inspect tool is not kubernetes_describe_workload")
    if inspect_data.get("permission_mode") != "READ_ONLY":
        errors.append("inspect permission mode is not READ_ONLY")
    if inspect_data.get("mutates_state") is not False:
        errors.append("inspect node mutates_state is not false")
    if inspect_data.get("operation_kind") != "kubernetes.workload.describe":
        errors.append("inspect operation kind is not kubernetes.workload.describe")
    if "kubernetes-safety" not in (inspect_data.get("skill_slugs") or []):
        errors.append("kubernetes-safety skill is not attached")
    forbidden_tools = _node_tool_names(nodes) & _FORBIDDEN_TOOLS
    if forbidden_tools:
        errors.append("forbidden tools present: " + ", ".join(sorted(forbidden_tools)))
    return errors
