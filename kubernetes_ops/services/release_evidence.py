from __future__ import annotations

import asyncio
import json
import urllib.parse
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from app.egress_redaction import redact_egress_text
from kubernetes_ops.models import K8sAppRef, K8sProvider, K8sWorkloadRef
from kubernetes_ops.services.provider_probe import probe_kubernetes_provider, probe_result_payload
from kubernetes_ops.services.readiness import build_kubernetes_readiness_report
from kubernetes_ops.services.release_action_controls import build_kubernetes_release_action_controls_evidence
from kubernetes_ops.services.release_admin_mode_safety import build_kubernetes_release_admin_mode_safety_evidence
from kubernetes_ops.services.release_artifact_safety import build_kubernetes_release_evidence_artifact_safety_report
from kubernetes_ops.services.release_audit_redaction import build_kubernetes_release_audit_redaction_evidence
from kubernetes_ops.services.release_backend_workstream import (
    build_kubernetes_release_backend_workstream,
    build_kubernetes_release_backend_workstream_blocker_groups,
    can_enable_kubernetes_release_sidebar,
)
from kubernetes_ops.services.release_blockers import build_kubernetes_release_blockers
from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION, build_kubernetes_release_contract
from kubernetes_ops.services.release_definition_of_done import build_kubernetes_release_definition_of_done
from kubernetes_ops.services.release_evidence_checklist import build_kubernetes_production_evidence_checklist
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
from kubernetes_ops.services.release_post_review_retention import (
    build_kubernetes_release_post_review_retention_evidence,
)
from kubernetes_ops.services.release_preflight import load_kubernetes_release_preflight_artifact
from kubernetes_ops.services.release_production_action_evidence import (
    load_kubernetes_production_action_evidence_artifact,
)
from kubernetes_ops.services.release_provider_secret_lifecycle import (
    build_kubernetes_release_provider_secret_lifecycle_evidence,
)
from kubernetes_ops.services.release_scope import build_kubernetes_release_scope_report
from kubernetes_ops.services.release_secret_read_controls import build_kubernetes_release_secret_read_controls_evidence
from kubernetes_ops.services.release_studio_diagnosis import build_kubernetes_release_studio_diagnosis_draft_evidence
from kubernetes_ops.services.release_summary import build_kubernetes_release_summary
from kubernetes_ops.services.sync import KubernetesSyncResult, sync_kubernetes_providers
from kubernetes_ops.studio_integration import owned_kubernetes_mcp_server
from studio.mcp_client import call_mcp_tool


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


def _apply_artifact_safety_pass(evidence: dict[str, Any], blockers: list) -> list:
    """Run the artifact-safety gate and refresh the derived summary/workstream.

    Adds the artifact_safety blocker at most once, then rebuilds
    release_summary / completion_audit / backend_workstream so they reflect
    the current blocker list.
    """
    artifact_safety = build_kubernetes_release_evidence_artifact_safety_report(evidence)
    if not artifact_safety.get("success") and not any(str(item).startswith("artifact_safety:") for item in blockers):
        blockers = [*blockers, f"artifact_safety:{artifact_safety.get('status') or 'failed'}"]
    evidence["artifact_safety"] = artifact_safety
    evidence["blockers"] = blockers
    evidence["production_ready"] = not blockers
    release_summary = build_kubernetes_release_summary(evidence)
    evidence["release_summary"] = release_summary
    evidence["completion_audit"] = release_summary.get("completion_audit") or {}
    _attach_backend_workstream(evidence)
    return blockers


def _attach_backend_workstream(evidence: dict[str, Any]) -> None:
    readiness = evidence.get("readiness") if isinstance(evidence.get("readiness"), dict) else {}
    production_gate = readiness.get("production_gate") if isinstance(readiness.get("production_gate"), dict) else {}
    completion_audit = evidence.get("completion_audit") if isinstance(evidence.get("completion_audit"), dict) else {}
    evidence["backend_workstream"] = build_kubernetes_release_backend_workstream(
        completion_audit=completion_audit,
        blocker_groups=build_kubernetes_release_backend_workstream_blocker_groups(evidence),
        production_evidence_checklist=build_kubernetes_production_evidence_checklist(production_gate=production_gate),
        can_enable_sidebar=can_enable_kubernetes_release_sidebar(
            production_ready=bool(evidence.get("production_ready")),
            ready_for_sidebar=bool(evidence.get("ready_for_sidebar")),
            completion_audit=completion_audit,
        ),
    )


def _provider_probe_evidence(enabled: bool) -> list[dict[str, Any]]:
    if not enabled:
        return [{"status": "skipped", "success": False, "reason": "provider probe skipped"}]
    providers = list(K8sProvider.objects.filter(enabled=True).order_by("kind", "name"))
    if not providers:
        return [{"status": "missing", "success": False, "reason": "no enabled providers"}]
    results: list[dict[str, Any]] = []
    for provider in providers:
        payload = probe_result_payload(probe_kubernetes_provider(provider))
        payload["path"] = _public_path(str(payload.get("path") or ""))
        payload["error"] = _redacted_text(payload.get("error"))
        payload["provider_base_url"] = _public_base_url(provider.base_url)
        results.append(payload)
    return results


def _sync_dry_run_evidence(enabled: bool) -> list[dict[str, Any]]:
    if not enabled:
        return [{"status": "skipped", "success": False, "reason": "sync dry-run skipped"}]
    results = sync_kubernetes_providers(dry_run=True)
    if not results:
        return [{"status": "missing", "success": False, "reason": "no enabled providers matched sync"}]
    return [_sync_result_payload(item) for item in results]


def _sync_result_payload(result: KubernetesSyncResult) -> dict[str, Any]:
    return {
        "provider_id": result.provider_id,
        "provider_name": result.provider_name,
        "provider_kind": result.provider_kind,
        "success": result.success,
        "dry_run": result.dry_run,
        "clusters": result.clusters,
        "namespaces": result.namespaces,
        "workloads": result.workloads,
        "pods": result.pods,
        "services": result.services,
        "ingresses": result.ingresses,
        "events": result.events,
        "apps": result.apps,
        "fleet_bundles": result.fleet_bundles,
        "error": _redacted_text(result.error),
    }


def _public_base_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    netloc = _safe_netloc(parsed)
    if not netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme, netloc, "", "", ""))[:300]


def _public_path(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or ""))
    if not parsed.scheme and not parsed.netloc:
        return urllib.parse.urlunsplit(("", "", parsed.path or "/", "", ""))[:300]
    netloc = _safe_netloc(parsed)
    if not netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))[:300]


def _safe_netloc(parsed: urllib.parse.SplitResult) -> str:
    host = parsed.hostname or ""
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    return f"{host}:{port}" if port else host


def _redacted_text(value: object) -> str:
    return redact_egress_text(str(value or "")).text[:1000]


def _studio_mcp_evidence(user, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "studio MCP call skipped"}
    mcp = owned_kubernetes_mcp_server(user)
    if mcp is None:
        return {"success": False, "status": "missing", "reason": "owned Kubernetes MCP server is missing"}
    target = _diagnosis_target()
    if target is None:
        return {
            "success": False,
            "status": "missing",
            "mcp_server": _mcp_summary(mcp),
            "reason": "no app/workload target for diagnosis smoke",
        }
    try:
        result = asyncio.run(call_mcp_tool(mcp, "kubernetes_describe_workload", target["arguments"]))
    except Exception as exc:
        return {
            "success": False,
            "status": "error",
            "mcp_server": _mcp_summary(mcp),
            "target": target,
            "error": str(exc),
        }
    policy = (result.get("structuredContent") or {}).get("policy", {})
    policy_errors = _studio_mcp_policy_errors(policy)
    success = not bool(result.get("isError")) and not policy_errors
    return {
        "success": success,
        "status": "ready" if success else ("error" if result.get("isError") else "policy_violation"),
        "mcp_server": _mcp_summary(mcp),
        "target": target,
        "content_items": len(result.get("content") or []),
        "policy": policy,
        "policy_errors": policy_errors,
        "content_preview": _content_preview(result),
    }


def _action_controls_evidence(user, enabled: bool) -> dict[str, Any]:
    return build_kubernetes_release_action_controls_evidence(user, enabled)


def _admin_mode_safety_evidence(user, enabled: bool) -> dict[str, Any]:
    return build_kubernetes_release_admin_mode_safety_evidence(user, enabled)


def _post_review_retention_evidence(user, enabled: bool) -> dict[str, Any]:
    return build_kubernetes_release_post_review_retention_evidence(user, enabled)


def _external_evidence_bundle(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "external evidence bundle skipped"}
    return load_kubernetes_external_evidence_bundle_artifact()


def _interactive_transport_evidence(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "interactive transport prerequisite evidence skipped"}
    return load_kubernetes_interactive_transport_evidence_artifact()


def _interactive_live_smoke_evidence(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "interactive live-smoke evidence skipped"}
    return load_kubernetes_interactive_live_smoke_artifact()


def _interactive_shell_streams_evidence(user, enabled: bool) -> dict[str, Any]:
    return build_kubernetes_release_interactive_shell_stream_evidence(user, enabled)


def _normal_user_surface_evidence(enabled: bool) -> dict[str, Any]:
    return build_kubernetes_release_normal_user_surface_evidence(enabled)


def _production_action_evidence(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "production action evidence skipped"}
    return load_kubernetes_production_action_evidence_artifact()


def _studio_diagnosis_draft_evidence(user, enabled: bool) -> dict[str, Any]:
    return build_kubernetes_release_studio_diagnosis_draft_evidence(user, enabled)


def _readonly_rbac_live_evidence(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"success": False, "status": "skipped", "reason": "read-only RBAC live proof skipped"}
    path = Path(settings.BASE_DIR) / "artifacts" / "kubernetes_ops_readonly_rbac_live_evidence.json"
    if not path.exists():
        return {
            "success": False,
            "status": "missing",
            "path": str(path),
            "reason": "run scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply before release approval",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "status": "error", "path": str(path), "error": str(exc)}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    allowed = payload.get("allowed") if isinstance(payload.get("allowed"), list) else []
    denied = payload.get("denied") if isinstance(payload.get("denied"), list) else []
    success = (
        payload.get("status") == "ready"
        and not errors
        and all(item.get("decision") == "yes" for item in allowed)
        and all(item.get("decision") == "no" for item in denied)
    )
    return {
        "success": success,
        "status": "ready" if success else str(payload.get("status") or "missing"),
        "path": str(path),
        "context": payload.get("context", ""),
        "applied": bool(payload.get("applied")),
        "service_account": payload.get("service_account", ""),
        "allowed_count": len(allowed),
        "denied_count": len(denied),
        "errors": errors,
        "checked_at": payload.get("checked_at", ""),
    }


def _mcp_summary(mcp) -> dict[str, Any]:
    return {
        "id": getattr(mcp, "id", None),
        "name": getattr(mcp, "name", ""),
        "transport": getattr(mcp, "transport", ""),
        "url": _public_base_url(getattr(mcp, "url", "")),
        "last_test_ok": getattr(mcp, "last_test_ok", None),
    }


def _diagnosis_target() -> dict[str, Any] | None:
    app = K8sAppRef.objects.select_related("cluster").order_by("id").first()
    if app is not None:
        return {
            "source": "app",
            "name": app.name,
            "namespace": app.namespace,
            "cluster": app.cluster.name,
            "arguments": {
                "cluster": _cluster_context(app.cluster),
                "namespace": app.namespace,
                "kind": _kind_from_labels(app.labels),
                "name": app.name,
            },
        }
    workload = K8sWorkloadRef.objects.select_related("cluster").order_by("id").first()
    if workload is None:
        return None
    return {
        "source": "workload",
        "name": workload.name,
        "namespace": workload.namespace,
        "cluster": workload.cluster.name,
        "arguments": {
            "cluster": _cluster_context(workload.cluster),
            "namespace": workload.namespace,
            "kind": workload.kind or "deployment",
            "name": workload.name,
        },
    }


def _cluster_context(cluster) -> str:
    labels = cluster.labels if isinstance(cluster.labels, dict) else {}
    return str(
        labels.get("kube_context") or labels.get("context") or labels.get("cluster_context") or cluster.name
    ).strip()


def _kind_from_labels(labels: dict[str, Any]) -> str:
    raw = str((labels or {}).get("workload_kind") or (labels or {}).get("kind") or "deployment").strip().lower()
    return {"deploy": "deployment", "deployments": "deployment", "pods": "pod"}.get(raw, raw)


def _content_preview(result: dict[str, Any]) -> str:
    content = result.get("content") or []
    if not content:
        return ""
    text = str((content[0] or {}).get("text") or "")
    return redact_egress_text(text).text[:800]


def _studio_mcp_policy_errors(policy: Any) -> list[str]:
    if not isinstance(policy, dict) or not policy:
        return ["missing policy"]
    errors: list[str] = []
    permission_mode = str(policy.get("permission_mode") or "").strip().upper()
    if permission_mode != "READ_ONLY":
        errors.append(f"permission_mode is {permission_mode or 'missing'}")
    if policy.get("mutates_state") is not False:
        errors.append("mutates_state is not false")
    if bool(policy.get("requires_approval")):
        errors.append("requires_approval is true")
    return errors
