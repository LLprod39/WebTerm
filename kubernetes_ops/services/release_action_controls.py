from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sAdminSession,
    K8sAppRef,
    K8sCluster,
    K8sFleetBundle,
    K8sPodRef,
    K8sWorkloadRef,
)
from kubernetes_ops.services.action_errors import ActionRequestValidationError
from kubernetes_ops.services.action_production_templates import production_rollout_restart_template_is_safe
from kubernetes_ops.services.action_requests import (
    approve_external_action_request,
    block_kubernetes_action_execution,
    create_kubernetes_action_request,
    record_external_action_verification,
)
from kubernetes_ops.services.action_rollback import rollback_plan_is_payload_safe
from kubernetes_ops.services.action_verification import (
    build_native_action_verification_plan,
    record_native_action_verification_evaluation,
)
from kubernetes_ops.services.admin_dry_run import manifest_fingerprint
from kubernetes_ops.services.admin_write_approval import production_write_restricted_credential_gate_report


def build_kubernetes_release_action_controls_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "action controls proof skipped"}
    if not user or not getattr(user, "is_staff", False):
        return {"success": False, "status": "missing", "reason": "staff user is required for action controls proof"}
    try:
        with transaction.atomic():
            suffix = uuid.uuid4().hex[:10]
            cluster = K8sCluster.objects.create(name=f"release-evidence-{suffix}", environment="test")
            restricted_gate_cluster = K8sCluster(name=f"release-evidence-prod-{suffix}", environment="prod")
            restricted_gate_missing = production_write_restricted_credential_gate_report(
                cluster=restricted_gate_cluster,
                namespace="payments",
                target_environment="production",
                evidence_ref="",
            )
            restricted_gate_ready = production_write_restricted_credential_gate_report(
                cluster=restricted_gate_cluster,
                namespace="payments",
                target_environment="production",
                evidence_ref="artifact:restricted-sa-proof",
            )
            workload = K8sWorkloadRef.objects.create(
                cluster=cluster,
                namespace="release-evidence",
                name="restart-smoke",
                kind=K8sWorkloadRef.KIND_DEPLOYMENT,
                health=K8sCluster.HEALTH_WARNING,
                ready=1,
                desired=2,
            )
            fleet_bundle = K8sFleetBundle.objects.create(
                name=f"release-evidence-bundle-{suffix}",
                source="https://git.example.test/platform/fleet.git",
                target="release-evidence",
                status=K8sFleetBundle.STATUS_ROLLING,
                ready=1,
                desired=2,
            )
            devtron_app = K8sAppRef.objects.create(
                cluster=cluster,
                namespace="release-evidence",
                name="rollback-smoke",
                owner=K8sAppRef.OWNER_DEVTRON,
                health=K8sCluster.HEALTH_WARNING,
                version="2026.07.01-1",
                links={"rollback": "https://devtron.example.test/app/rollback?token=release-secret-token"},
            )
            dry_run_session = K8sAdminSession.objects.create(
                user=user,
                username_snapshot=getattr(user, "username", ""),
                cluster=cluster,
                mode=K8sAdminSession.MODE_WRITE,
                status=K8sAdminSession.STATUS_ACTIVE,
                risk_tier=K8sAdminSession.RISK_HIGH,
                allowed_verbs=["dry_run_apply", "apply"],
                allowed_kinds=["Deployment"],
                allowed_namespaces=["release-evidence"],
                reason="release evidence apply action request smoke",
                approval_ref="CHG-RELEASE-EVIDENCE",
                approved_by=user,
                approved_at=timezone.now(),
                expires_at=timezone.now() + timedelta(minutes=30),
            )
            apply_manifest = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "restart-smoke", "namespace": "release-evidence"},
                "spec": {"replicas": 2},
            }
            dry_run_proof = K8sAdminAction.objects.create(
                session=dry_run_session,
                user=user,
                username_snapshot=getattr(user, "username", ""),
                cluster=cluster,
                namespace="release-evidence",
                resource_api_version="apps/v1",
                resource_kind="Deployment",
                resource_name="restart-smoke",
                verb=K8sAdminAction.VERB_DRY_RUN_APPLY,
                status=K8sAdminAction.STATUS_DRY_RUN,
                request_payload_sanitized={
                    "target": {
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "resource": "deployments",
                        "namespace": "release-evidence",
                        "name": "restart-smoke",
                    },
                    "manifest_fingerprint": manifest_fingerprint(apply_manifest),
                    "submitted_top_level_fields": sorted(apply_manifest.keys()),
                    "redacted": False,
                },
                diff_summary={"available": True, "changed": True},
                response_summary={"dry_run": True},
            )
            apply_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_APPLY,
                    "reason": "release evidence apply request smoke",
                    "target": {
                        "cluster_id": f"cluster_{cluster.id}",
                        "dry_run_action_id": str(dry_run_proof.action_id),
                        "manifest": {"token": "release-secret-token"},
                    },
                },
            )
            action_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                    "reason": "release evidence action controls smoke",
                    "target": {"workload_id": f"workload_{workload.id}", "token": "release-secret-token"},
                },
            )
            scale_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_K8S_WORKLOAD_SCALE,
                    "reason": "release evidence scale smoke",
                    "target": {
                        "workload_id": f"workload_{workload.id}",
                        "replicas": 2,
                        "token": "release-secret-token",
                    },
                },
            )
            patch_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_PATCH,
                    "reason": "release evidence patch smoke",
                    "target": {
                        "cluster_id": f"cluster_{cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "release-evidence",
                        "name": "restart-smoke",
                        "patch_type": "merge",
                        "patch_body": {"metadata": {"annotations": {"webterm.io/release-evidence": "true"}}},
                    },
                },
            )
            delete_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_K8S_RESOURCE_DELETE,
                    "reason": "release evidence delete request smoke",
                    "target": {
                        "cluster_id": f"cluster_{cluster.id}",
                        "api_version": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "release-evidence",
                        "name": "restart-smoke",
                        "confirmation": "delete Deployment release-evidence/restart-smoke",
                        "propagation_policy": "Foreground",
                    },
                },
            )
            fleet_pause_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_FLEET_ROLLOUT_PAUSE,
                    "reason": "release evidence fleet pause smoke",
                    "target": {"bundle_id": f"fleet_{fleet_bundle.id}", "token": "release-secret-token"},
                },
            )
            fleet_resume_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_FLEET_ROLLOUT_RESUME,
                    "reason": "release evidence fleet resume smoke",
                    "target": {"bundle_name": fleet_bundle.name},
                },
            )
            devtron_rollback_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_DEVTRON_OPEN_ROLLBACK,
                    "reason": "release evidence devtron rollback smoke",
                    "target": {"app_id": f"app_{devtron_app.id}"},
                },
            )
            approved_request = approve_external_action_request(
                action_request=action_request,
                user=user,
                data={
                    "approval_ref": "CHG-RELEASE-EVIDENCE",
                    "summary": "release evidence external approval smoke",
                },
            )
            approval_status = approved_request.status
            approval_recorded = bool(approved_request.execution_policy.get("external_approval_recorded"))
            verified_request = record_external_action_verification(
                action_request=approved_request,
                user=user,
                data={
                    "outcome": "succeeded",
                    "summary": "external rollout verification completed",
                    "external_ref": "https://rancher.example.test/dashboard",
                    "checks": ["workload rollout status", "pod readiness"],
                    "evidence": {"ready": "2/2", "token": "release-secret-token"},
                },
            )
            terminal_execute_rejected = _terminal_execute_rejected(verified_request, user)
            blocked_request = _blocked_execution_request(user, workload)
            terminal_verify_rejected = _terminal_verify_rejected(blocked_request, user)
            restart_verification_plan = build_native_action_verification_plan(
                action_request=action_request,
                execution={
                    "operation": "restart",
                    "target": action_request.target,
                    "action": {"status": K8sAdminAction.STATUS_COMPLETED},
                },
            )
            apply_verification_plan = build_native_action_verification_plan(
                action_request=apply_request,
                execution={
                    "operation": "apply",
                    "target": apply_request.target,
                    "action": {"status": K8sAdminAction.STATUS_COMPLETED},
                },
            )
            native_action = K8sAdminAction.objects.create(
                session=dry_run_session,
                user=user,
                username_snapshot=getattr(user, "username", ""),
                cluster=cluster,
                namespace="release-evidence",
                resource_api_version="apps/v1",
                resource_kind="Deployment",
                resource_name="restart-smoke",
                verb=K8sAdminAction.VERB_RESTART,
                status=K8sAdminAction.STATUS_COMPLETED,
                request_payload_sanitized={"reason": "release evidence native verification smoke"},
                response_summary={"source": "release_evidence_native_verification"},
            )
            native_evaluation_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
                    "reason": "release evidence native verification auto smoke",
                    "target": {"workload_id": f"workload_{workload.id}"},
                },
            )
            executed_at = timezone.now()
            fresh_sync = executed_at + timedelta(seconds=1)
            cluster.last_sync_at = fresh_sync
            cluster.save(update_fields=["last_sync_at", "updated_at"])
            workload.ready = 2
            workload.desired = 2
            workload.health = K8sCluster.HEALTH_HEALTHY
            workload.last_sync_at = fresh_sync
            workload.save(update_fields=["ready", "desired", "health", "last_sync_at", "updated_at"])
            K8sPodRef.objects.create(
                cluster=cluster,
                namespace="release-evidence",
                name="restart-smoke-7f8c9",
                health=K8sCluster.HEALTH_HEALTHY,
                phase="Running",
                owner_kind="ReplicaSet",
                owner_name="restart-smoke",
                ready_containers=1,
                total_containers=1,
                last_sync_at=fresh_sync,
            )
            native_evaluation_request.status = K8sActionRequest.STATUS_EXECUTED_NATIVE
            native_evaluation_request.report = {
                "status": K8sActionRequest.STATUS_EXECUTED_NATIVE,
                "executed_at": executed_at.isoformat(),
                "native_execution_performed_by_webterm": True,
                "admin_action_id": str(native_action.action_id),
                "verification_plan": build_native_action_verification_plan(
                    action_request=native_evaluation_request,
                    execution={
                        "operation": "restart",
                        "target": native_evaluation_request.target,
                        "action": {"id": str(native_action.action_id), "status": K8sAdminAction.STATUS_COMPLETED},
                    },
                    created_at=executed_at,
                ),
            }
            native_evaluation_request.execution_policy = {
                "native_execution_enabled": True,
                "native_execution_performed_by_webterm": True,
            }
            native_evaluation_request.save(update_fields=["status", "report", "execution_policy", "updated_at"])
            native_evaluated_request = record_native_action_verification_evaluation(
                action_request=native_evaluation_request,
                evaluated_by="release-action-controls",
            )
            gitops_request = create_kubernetes_action_request(
                user=user,
                data={
                    "action": K8sActionRequest.ACTION_GITOPS_CREATE_MERGE_REQUEST,
                    "reason": "release evidence gitops merge request smoke",
                    "target": {
                        "cluster_id": f"cluster_{cluster.id}",
                        "repository": "https://gitlab.example.test/platform/charts.git?token=release-secret-token",
                        "source_branch": "webterm/release-evidence",
                        "target_branch": "main",
                        "path": "charts/release-evidence/values.yaml",
                        "title": "Release evidence GitOps smoke",
                        "diff_summary": "Update image tag through GitOps merge request.",
                    },
                },
            )
            production_restart_template = action_request.preview.get("production_rollout_restart_template") or {}
            proof = {
                "success": True,
                "status": "ready",
                "mode": "transaction_rollback",
                "created_request_status": K8sActionRequest.STATUS_PENDING_APPROVAL,
                "approval_status": approval_status,
                "approval_recorded": approval_recorded,
                "preview_blast_radius": action_request.preview.get("blast_radius"),
                "scale_request_status": scale_request.status,
                "scale_preview_blast_radius": scale_request.preview.get("blast_radius"),
                "scale_preview_replicas": scale_request.preview.get("replicas"),
                "scale_target_redacted": scale_request.target.get("token", "[redacted]") == "[redacted]",
                "apply_request_status": apply_request.status,
                "apply_preview_blast_radius": apply_request.preview.get("blast_radius"),
                "apply_manifest_not_stored": "manifest" not in apply_request.target
                and "release-secret-token" not in str(apply_request.target),
                "apply_dry_run_proof_linked": apply_request.target.get("dry_run_action_id")
                == str(dry_run_proof.action_id),
                "patch_request_status": patch_request.status,
                "patch_preview_blast_radius": patch_request.preview.get("blast_radius"),
                "patch_preview_shape": patch_request.preview.get("patch_shape", {}).get("body_shape"),
                "delete_request_status": delete_request.status,
                "delete_preview_blast_radius": delete_request.preview.get("blast_radius"),
                "delete_confirmation_stored": delete_request.target.get("confirmation")
                == "delete Deployment release-evidence/restart-smoke",
                "rollback_plan_status": (action_request.preview.get("rollback_plan") or {}).get("status"),
                "production_restart_template_status": production_restart_template.get("status"),
                "production_restart_template_approval_required": bool(
                    (production_restart_template.get("approval") or {}).get("required")
                ),
                "production_restart_template_verification_required": bool(
                    (production_restart_template.get("verification") or {}).get("required")
                ),
                "production_restart_template_report_required": bool(
                    (production_restart_template.get("report") or {}).get("required")
                ),
                "production_restart_template_safe": production_rollout_restart_template_is_safe(
                    production_restart_template
                ),
                "rollback_scale_previous_replicas": (scale_request.preview.get("rollback_plan") or {}).get(
                    "previous_replicas"
                ),
                "rollback_apply_requires_dry_run": "rollback_dry_run_action_id"
                in list((apply_request.preview.get("rollback_plan") or {}).get("evidence_required") or []),
                "rollback_delete_requires_restore_source": "restore_source_ref"
                in list((delete_request.preview.get("rollback_plan") or {}).get("evidence_required") or []),
                "rollback_plan_payload_safe": all(
                    rollback_plan_is_payload_safe(request.preview.get("rollback_plan") or {})
                    for request in [action_request, scale_request, apply_request, patch_request, delete_request]
                ),
                "native_execution_enabled": bool(approved_request.execution_policy.get("native_execution_enabled")),
                "external_verification_status": verified_request.status,
                "external_verification_redacted": verified_request.report.get("evidence", {}).get("token")
                == "[redacted]",
                "terminal_execute_rejected": terminal_execute_rejected,
                "blocked_execution_status": blocked_request.status,
                "blocked_execution_verified": bool(blocked_request.report.get("verified")),
                "terminal_verify_rejected": terminal_verify_rejected,
                "native_verification_plan_status": restart_verification_plan.get("status"),
                "native_verification_plan_check_ids": list(restart_verification_plan.get("check_ids") or []),
                "apply_verification_plan_check_ids": list(apply_verification_plan.get("check_ids") or []),
                "native_verification_auto_status": (native_evaluated_request.report.get("verification_plan") or {}).get(
                    "status"
                ),
                "native_verification_auto_request_status": native_evaluated_request.status,
                "native_verification_auto_recorded": bool(
                    native_evaluated_request.execution_policy.get("native_verification_auto_recorded")
                ),
                "native_verification_auto_check_statuses": [
                    item.get("status")
                    for item in (native_evaluated_request.report.get("verification_plan") or {}).get("checks", [])
                    if isinstance(item, dict)
                ],
                "restricted_write_gate_required": bool(restricted_gate_missing.get("required")),
                "restricted_write_gate_blocks_without_ref": restricted_gate_missing.get("blocker")
                == "restricted_credential_evidence_required",
                "restricted_write_gate_allows_with_ref": bool(
                    restricted_gate_ready.get("ready") and restricted_gate_ready.get("evidence_ref_present")
                ),
                "restricted_write_gate_setting": restricted_gate_missing.get("setting"),
                "restricted_write_gate_target_environment": restricted_gate_missing.get("target_environment"),
                "native_verification_plan_payload_safe": not restart_verification_plan.get("payload_stored")
                and not apply_verification_plan.get("payload_stored")
                and not (native_evaluated_request.report.get("verification_plan") or {}).get("payload_stored")
                and "release-secret-token" not in str(restart_verification_plan)
                and "release-secret-token" not in str(apply_verification_plan)
                and "release-secret-token" not in str(native_evaluated_request.report),
                "gitops_request_status": gitops_request.status,
                "gitops_preview_blast_radius": gitops_request.preview.get("blast_radius"),
                "gitops_native_execution_mode": gitops_request.execution_policy.get("native_execution_mode"),
                "gitops_repository_sanitized": "release-secret-token" not in str(gitops_request.target),
                "gitops_merge_request_template": bool(gitops_request.preview.get("merge_request_template")),
                "gitops_provider": gitops_request.preview.get("git_provider"),
                "gitops_write_performed": bool(gitops_request.preview.get("gitops_write_performed")),
                "gitops_cluster_mutation_performed": bool(gitops_request.preview.get("cluster_mutation_performed")),
                "gitops_gitlab_payload_ready": bool(
                    (gitops_request.preview.get("merge_request_template") or {}).get("api_payload")
                ),
                "gitops_merge_request_draft": bool(
                    (gitops_request.preview.get("merge_request_template") or {}).get("draft")
                ),
                "gitops_merge_request_removes_source_branch": bool(
                    (gitops_request.preview.get("merge_request_template") or {}).get("remove_source_branch")
                ),
                "gitops_verification_plan_check_ids": list(
                    (gitops_request.preview.get("merge_request_template") or {}).get("verification_plan") or []
                ),
                "fleet_pause_request_status": fleet_pause_request.status,
                "fleet_pause_preview_blast_radius": fleet_pause_request.preview.get("blast_radius"),
                "fleet_pause_target_redacted": fleet_pause_request.target.get("token", "[redacted]") == "[redacted]",
                "fleet_resume_request_status": fleet_resume_request.status,
                "fleet_resume_preview_blast_radius": fleet_resume_request.preview.get("blast_radius"),
                "devtron_rollback_request_status": devtron_rollback_request.status,
                "devtron_rollback_preview_blast_radius": devtron_rollback_request.preview.get("blast_radius"),
                "devtron_rollback_execution_mode": devtron_rollback_request.execution_policy.get(
                    "native_execution_mode"
                ),
                "devtron_rollback_links_sanitized": "release-secret-token"
                not in str(devtron_rollback_request.preview.get("links")),
                "persistent_rows": False,
            }
            transaction.set_rollback(True)
            return proof
    except Exception as exc:
        return {"success": False, "status": "error", "error": str(exc)}


def _terminal_execute_rejected(action_request: K8sActionRequest, user) -> bool:
    try:
        block_kubernetes_action_execution(action_request=action_request, user=user)
    except ActionRequestValidationError as exc:
        return exc.code == "action_request_not_pending"
    return False


def _blocked_execution_request(user, workload: K8sWorkloadRef) -> K8sActionRequest:
    request = create_kubernetes_action_request(
        user=user,
        data={
            "action": K8sActionRequest.ACTION_K8S_ROLLOUT_RESTART,
            "reason": "release evidence execution block smoke",
            "target": {"workload_id": f"workload_{workload.id}"},
        },
    )
    request = approve_external_action_request(
        action_request=request,
        user=user,
        data={
            "approval_ref": "CHG-RELEASE-EVIDENCE-BLOCK",
            "summary": "release evidence blocked execution approval smoke",
        },
    )
    return block_kubernetes_action_execution(action_request=request, user=user)


def _terminal_verify_rejected(action_request: K8sActionRequest, user) -> bool:
    try:
        record_external_action_verification(
            action_request=action_request,
            user=user,
            data={"outcome": "succeeded", "summary": "terminal rewrite smoke"},
        )
    except ActionRequestValidationError as exc:
        return exc.code == "action_request_not_pending"
    return False
