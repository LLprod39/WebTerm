from __future__ import annotations

from typing import Any

from django.utils import timezone

from kubernetes_ops.services.provider_probe import probe_kubernetes_provider
from kubernetes_ops.services.readiness import build_kubernetes_readiness_report
from kubernetes_ops.services.release_audit_redaction import build_kubernetes_release_audit_redaction_evidence
from kubernetes_ops.services.release_blockers import build_kubernetes_release_blockers
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION, build_kubernetes_release_contract
from kubernetes_ops.services.release_definition_of_done import build_kubernetes_release_definition_of_done
from kubernetes_ops.services.release_evidence_helpers import (
    _action_controls_evidence,
    _admin_mode_safety_evidence,
    _apply_artifact_safety_pass,
    _attach_backend_workstream,
    _external_evidence_bundle,
    _interactive_live_smoke_evidence,
    _interactive_shell_streams_evidence,
    _interactive_transport_evidence,
    _normal_user_surface_evidence,
    _post_review_retention_evidence,
    _production_action_evidence,
    _provider_probe_evidence,
    _readonly_rbac_live_evidence,
    _studio_diagnosis_draft_evidence,
    _studio_mcp_evidence,
    _sync_dry_run_evidence,
)
from kubernetes_ops.services.release_external_evidence_bundle import load_kubernetes_external_evidence_bundle_artifact
from kubernetes_ops.services.release_handoff_plan import build_kubernetes_release_evidence_execution_plan
from kubernetes_ops.services.release_interactive_live_smoke import load_kubernetes_interactive_live_smoke_artifact
from kubernetes_ops.services.release_interactive_shell_streams import (
    build_kubernetes_release_interactive_shell_stream_evidence,
)
from kubernetes_ops.services.release_interactive_transport_evidence import (
    load_kubernetes_interactive_transport_evidence_artifact,
)
from kubernetes_ops.services.release_normal_user_surface import build_kubernetes_release_normal_user_surface_evidence
from kubernetes_ops.services.release_preflight import load_kubernetes_release_preflight_artifact
from kubernetes_ops.services.release_provider_secret_lifecycle import (
    build_kubernetes_release_provider_secret_lifecycle_evidence,
)
from kubernetes_ops.services.release_scope import build_kubernetes_release_scope_report
from kubernetes_ops.services.release_secret_read_controls import build_kubernetes_release_secret_read_controls_evidence
from kubernetes_ops.services.sync import KubernetesSyncResult, sync_kubernetes_providers
from kubernetes_ops.studio_integration import owned_kubernetes_mcp_server
from studio.mcp.mcp_client import call_mcp_tool

# Public/test re-exports (helpers resolve monkeypatches through this facade).
__all__ = [
    "KubernetesSyncResult",
    "RELEASE_EVIDENCE_SCHEMA_VERSION",
    "_attach_backend_workstream",
    "build_kubernetes_readiness_report",
    "build_kubernetes_release_evidence",
    "build_kubernetes_release_interactive_shell_stream_evidence",
    "build_kubernetes_release_normal_user_surface_evidence",
    "call_mcp_tool",
    "load_kubernetes_external_evidence_bundle_artifact",
    "load_kubernetes_interactive_live_smoke_artifact",
    "load_kubernetes_interactive_transport_evidence_artifact",
    "load_kubernetes_release_preflight_artifact",
    "owned_kubernetes_mcp_server",
    "probe_kubernetes_provider",
    "sync_kubernetes_providers",
]


def build_kubernetes_release_evidence(
    *,
    user,
    run_provider_probe: bool = True,
    run_sync_dry_run: bool = True,
    run_mcp_call: bool = True,
    run_action_controls: bool = True,
    run_admin_mode_safety: bool = True,
    run_post_review_retention: bool = True,
    run_external_evidence_bundle: bool = True,
    run_interactive_transport_evidence: bool = True,
    run_interactive_live_smoke: bool = True,
    run_interactive_shell_streams: bool = True,
    run_normal_user_surface: bool = True,
    run_readonly_rbac_live: bool = True,
    run_secret_read_controls: bool = True,
    run_provider_secret_lifecycle: bool = True,
    run_audit_redaction: bool = True,
    run_production_action_evidence: bool = True,
) -> dict[str, Any]:
    readiness = build_kubernetes_readiness_report(user=user, include_release_artifact_gate=False)
    provider_probes = _provider_probe_evidence(run_provider_probe)
    sync_dry_run = _sync_dry_run_evidence(run_sync_dry_run)
    studio_mcp = _studio_mcp_evidence(user, run_mcp_call)
    studio_diagnosis_draft = _studio_diagnosis_draft_evidence(user, run_mcp_call)
    action_controls = _action_controls_evidence(user, run_action_controls)
    admin_mode_safety = _admin_mode_safety_evidence(user, run_admin_mode_safety)
    post_review_retention = _post_review_retention_evidence(user, run_post_review_retention)
    external_evidence_bundle = _external_evidence_bundle(run_external_evidence_bundle)
    interactive_transport_evidence = _interactive_transport_evidence(run_interactive_transport_evidence)
    interactive_live_smoke = _interactive_live_smoke_evidence(run_interactive_live_smoke)
    interactive_shell_streams = _interactive_shell_streams_evidence(user, run_interactive_shell_streams)
    normal_user_surface = _normal_user_surface_evidence(run_normal_user_surface)
    secret_read_controls = build_kubernetes_release_secret_read_controls_evidence(user, run_secret_read_controls)
    provider_secret_lifecycle = build_kubernetes_release_provider_secret_lifecycle_evidence(
        run_provider_secret_lifecycle
    )
    audit_redaction = build_kubernetes_release_audit_redaction_evidence(run_audit_redaction)
    production_action_evidence = _production_action_evidence(run_production_action_evidence)
    readonly_rbac_live = _readonly_rbac_live_evidence(run_readonly_rbac_live)
    preflight = load_kubernetes_release_preflight_artifact()
    release_scope = build_kubernetes_release_scope_report(
        provider_probes=provider_probes,
        sync_dry_run=sync_dry_run,
        readonly_rbac_live=readonly_rbac_live,
        studio_mcp=studio_mcp,
    )
    readiness_evidence = {
        "status": readiness.get("status"),
        "summary": readiness.get("summary"),
        "checks": readiness.get("checks", []),
        "worker_state": readiness.get("worker_state", {}),
        "access_model": readiness.get("access_model", {}),
        "identity_runtime": readiness.get("identity_runtime", {}),
        "production_gate": readiness.get("production_gate", {}),
    }
    evidence_context = {
        "readiness": readiness_evidence,
        "provider_probes": provider_probes,
        "sync_dry_run": sync_dry_run,
        "action_controls": action_controls,
        "admin_mode_safety": admin_mode_safety,
        "post_review_retention": post_review_retention,
        "interactive_transport_evidence": interactive_transport_evidence,
        "interactive_live_smoke": interactive_live_smoke,
        "interactive_shell_streams": interactive_shell_streams,
        "normal_user_surface": normal_user_surface,
        "secret_read_controls": secret_read_controls,
        "provider_secret_lifecycle": provider_secret_lifecycle,
        "audit_redaction": audit_redaction,
        "production_action_evidence": production_action_evidence,
        "readonly_rbac_live": readonly_rbac_live,
        "preflight": preflight,
        "release_scope": release_scope,
    }
    definition_of_done = build_kubernetes_release_definition_of_done(evidence_context)
    blockers = build_kubernetes_release_blockers(
        readiness=readiness,
        provider_probes=provider_probes,
        sync_dry_run=sync_dry_run,
        studio_mcp=studio_mcp,
        studio_diagnosis_draft=studio_diagnosis_draft,
        action_controls=action_controls,
        admin_mode_safety=admin_mode_safety,
        post_review_retention=post_review_retention,
        external_evidence_bundle=external_evidence_bundle,
        interactive_transport_evidence=interactive_transport_evidence,
        interactive_live_smoke=interactive_live_smoke,
        interactive_shell_streams=interactive_shell_streams,
        normal_user_surface=normal_user_surface,
        secret_read_controls=secret_read_controls,
        provider_secret_lifecycle=provider_secret_lifecycle,
        audit_redaction=audit_redaction,
        production_action_evidence=production_action_evidence,
        readonly_rbac_live=readonly_rbac_live,
        preflight=preflight,
        release_scope=release_scope,
        definition_of_done=definition_of_done,
    )
    evidence = {
        "success": True,
        "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "operator": {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", ""),
            "is_staff": bool(getattr(user, "is_staff", False)),
        },
        "production_ready": False,
        "ready_for_sidebar": bool(readiness.get("ready_for_sidebar")),
        "enablement": {
            "env_flag": "KUBERNETES_OPS_READY_FOR_SIDEBAR",
            "env_flag_required": not bool(readiness.get("ready_for_sidebar")),
            "note": "Set KUBERNETES_OPS_READY_FOR_SIDEBAR=true only after production evidence is green.",
        },
        "readiness": readiness_evidence,
        "provider_probes": provider_probes,
        "sync_dry_run": sync_dry_run,
        "studio_mcp": studio_mcp,
        "studio_diagnosis_draft": studio_diagnosis_draft,
        "action_controls": action_controls,
        "admin_mode_safety": admin_mode_safety,
        "post_review_retention": post_review_retention,
        "external_evidence_bundle": external_evidence_bundle,
        "interactive_transport_evidence": interactive_transport_evidence,
        "interactive_live_smoke": interactive_live_smoke,
        "interactive_shell_streams": interactive_shell_streams,
        "normal_user_surface": normal_user_surface,
        "secret_read_controls": secret_read_controls,
        "provider_secret_lifecycle": provider_secret_lifecycle,
        "audit_redaction": audit_redaction,
        "production_action_evidence": production_action_evidence,
        "readonly_rbac_live": readonly_rbac_live,
        "preflight": preflight,
        "release_scope": release_scope,
        "definition_of_done": definition_of_done,
        "release_contract": build_kubernetes_release_contract(),
        "blockers": blockers,
    }
    # The artifact-safety gate re-runs after every enrichment step (summary,
    # backend workstream, execution plan) because each step adds new content
    # that must also pass redaction/safety checks.
    blockers = _apply_artifact_safety_pass(evidence, blockers)
    blockers = _apply_artifact_safety_pass(evidence, blockers)
    evidence["production_execution_plan"] = build_kubernetes_release_evidence_execution_plan(evidence)
    blockers = _apply_artifact_safety_pass(evidence, blockers)
    evidence["production_execution_plan"] = build_kubernetes_release_evidence_execution_plan(evidence)
    return evidence
