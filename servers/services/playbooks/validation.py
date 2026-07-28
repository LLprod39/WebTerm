"""Context-bound, revision-based playbook validation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from typing import Any

from django.db import transaction
from django.utils import timezone

from servers.models import BackgroundWorkerState, PlaybookValidation
from servers.services.ansible_engine import detect_ansible
from servers.services.ansible_validator_client import (
    AnsibleValidatorError,
    validator_runtime_metadata,
    validator_socket_path,
)
from servers.services.playbook_compatibility_analysis import (
    COMPATIBILITY_ANALYZER_VERSION,
)
from servers.services.playbook_compatibility_inventory import normalize_inventory_bindings
from servers.services.playbook_compatibility_validation import (
    build_execution_readiness,
    enforce_runtime_digest_match,
    validate_playbook_syntax,
)
from servers.services.playbook_runner import resolve_target_servers
from servers.services.playbooks.audit import record_playbook_event
from servers.services.playbooks.bundle_runtime import (
    BundleRuntimeError,
    apply_runtime_bundle_evidence,
    load_revision_runtime_bundle,
)
from servers.services.playbooks.compatibility import compatibility_for_revision
from servers.services.playbooks.target_identity import target_connection_identity_hashes


class PlaybookValidationError(ValueError):
    pass


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _active_execution_worker_fingerprint() -> dict[str, Any] | None:
    state = (
        BackgroundWorkerState.objects.filter(
            worker_kind="playbook_execution",
            status=BackgroundWorkerState.STATUS_RUNNING,
            lease_expires_at__gt=timezone.now(),
        )
        .order_by("-heartbeat_at")
        .first()
    )
    summary = state.last_summary if state is not None and isinstance(state.last_summary, dict) else {}
    fingerprint = summary.get("runtime_fingerprint") if isinstance(summary, dict) else None
    if not isinstance(fingerprint, dict):
        return None
    if not fingerprint.get("available") or not str(fingerprint.get("runtime_digest") or ""):
        return None
    return dict(fingerprint)


def runtime_fingerprint() -> dict[str, Any]:
    if validator_socket_path():
        image = os.getenv("WEBTERM_ANSIBLE_IMAGE", "webterm-ansible:latest")
        try:
            runtime = validator_runtime_metadata()
            available = True
        except AnsibleValidatorError:
            runtime = {}
            available = False
        digest = str(runtime.get("runtime_digest") or "")
        python_packages = runtime.get("python_packages") if isinstance(runtime.get("python_packages"), list) else []
        ansible_version = next(
            (
                str(item.get("version") or "")
                for item in python_packages
                if isinstance(item, dict) and item.get("name") == "ansible-core"
            ),
            "",
        )
        config_seed = "\n".join([image, digest, "isolated-validator-v2"])
        return {
            "method": "isolated-validator",
            "available": available,
            "ansible_version": ansible_version,
            "python_version": str(runtime.get("python") or ""),
            "image": image,
            "image_ready": available,
            "runtime_digest": digest,
            "collections": runtime.get("collections") if available else [],
            "config_hash": hashlib.sha256(config_seed.encode("utf-8")).hexdigest(),
            "analyzer_version": COMPATIBILITY_ANALYZER_VERSION,
        }
    worker_fingerprint = _active_execution_worker_fingerprint()
    if worker_fingerprint is not None:
        return worker_fingerprint
    detection = detect_ansible()
    config_seed = "\n".join(
        [
            os.getenv("WEBTERM_ANSIBLE_IMAGE", ""),
            os.getenv("ANSIBLE_CONFIG", ""),
            os.getenv("ANSIBLE_COLLECTIONS_PATH", ""),
        ]
    )
    return {
        "method": str(detection.get("method") or "none"),
        "available": bool(detection.get("available")),
        "ansible_version": str(detection.get("version") or ""),
        "python_version": platform.python_version(),
        "image": str(detection.get("image") or ""),
        "image_ready": detection.get("image_ready"),
        "config_hash": hashlib.sha256(config_seed.encode("utf-8")).hexdigest(),
        "analyzer_version": COMPATIBILITY_ANALYZER_VERSION,
    }


def _resolved_validation_context(
    profile,
    user,
    *,
    target_server_ids: list[int] | None,
    target_group_ids: list[int] | None,
    inventory_bindings: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, list[int]]], list[Any], list[str]]:
    mappings = normalize_inventory_bindings(
        inventory_bindings if inventory_bindings is not None else profile.selector_mappings if profile else {}
    )
    servers_by_id: dict[int, Any] = {}
    resolved: dict[str, dict[str, list[int]]] = {}
    for selector, binding in mappings.items():
        servers = resolve_target_servers(
            user,
            server_ids=binding.get("server_ids") or [],
            group_ids=binding.get("group_ids") or [],
        )
        ids = sorted({server.id for server in servers})
        resolved[selector] = {"server_ids": ids, "group_ids": []}
        servers_by_id.update({server.id: server for server in servers})
    explicit_targets = target_server_ids is not None or target_group_ids is not None
    if explicit_targets:
        target_servers = resolve_target_servers(
            user,
            server_ids=target_server_ids or [],
            group_ids=target_group_ids or [],
        )
    else:
        target_servers = list(servers_by_id.values())
    selected_ids = {server.id for server in target_servers}
    outside = sorted(
        selector
        for selector, binding in resolved.items()
        if not set(binding.get("server_ids") or []).issubset(selected_ids)
    )
    return resolved, target_servers, outside


def _enrich_issue(issue: dict[str, Any]) -> dict[str, Any]:
    code = str(issue.get("code") or "validation_issue")
    stage = {
        "invalid_yaml": "parse",
        "literal_secret": "secret_scan",
        "missing_role_bundle": "dependencies",
        "missing_project_asset": "dependencies",
        "unbound_host_selector": "bindings",
        "required_variables": "variables",
        "target_os_mismatch": "targets",
        "runtime_mismatch": "runtime",
    }.get(code, "static_analysis")
    return {
        "code": code,
        "severity": str(issue.get("severity") or "warning"),
        "stage": stage,
        "message": str(issue.get("message") or code),
        "remediation": str(
            issue.get("remediation") or "Review this validation stage and update the draft or run profile."
        ),
        "path": str(issue.get("path") or ""),
        "line": issue.get("line"),
        "column": issue.get("column"),
        "retryable": bool(issue.get("retryable", False)),
        "details": issue.get("details") if isinstance(issue.get("details"), dict) else {},
    }


def _target_signature(servers: list[Any], inventory_bindings: dict[str, Any] | None = None) -> str:
    connection_identities = target_connection_identity_hashes(servers)
    server_payload = [
        {
            "id": server.id,
            "detected_os": str(getattr(server, "detected_os", "") or ""),
            "active": bool(getattr(server, "is_active", False)),
            "connection_identity": connection_identities.get(str(server.id), ""),
        }
        for server in sorted(servers, key=lambda item: item.id)
    ]
    bindings = normalize_inventory_bindings(inventory_bindings or {})
    binding_payload = {
        selector: {
            "server_ids": sorted(binding.get("server_ids") or []),
            "group_ids": sorted(binding.get("group_ids") or []),
        }
        for selector, binding in sorted(bindings.items())
    }
    payload = {"servers": server_payload, "bindings": binding_payload}
    return _hash_payload(payload) if server_payload or binding_payload else ""


def target_signature_for_servers(servers: list[Any], inventory_bindings: dict[str, Any] | None = None) -> str:
    return _target_signature(servers, inventory_bindings)


def validation_is_fresh(
    validation,
    *,
    revision,
    binding_profile,
    servers: list[Any],
    inventory_bindings: dict[str, Any] | None = None,
    fingerprint: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if validation.status != PlaybookValidation.STATUS_READY:
        return False, f"Validation status is {validation.status}"
    if validation.revision_id != revision.id:
        return False, "Validation belongs to another revision"
    if validation.binding_profile_id != (binding_profile.id if binding_profile else None):
        return False, "Validation belongs to another binding profile"
    if validation.binding_version != (binding_profile.version if binding_profile else None):
        return False, "Binding profile changed after validation"
    if validation.target_signature != target_signature_for_servers(servers, inventory_bindings):
        return False, "Target set or inventory bindings changed after validation"
    current_fingerprint = fingerprint or runtime_fingerprint()
    if validation.runtime_fingerprint_hash != _hash_payload(current_fingerprint):
        return False, "Ansible runtime changed after validation"
    return True, ""


@transaction.atomic
def validate_revision(
    *,
    revision,
    user,
    binding_profile=None,
    target_server_ids: list[int] | None = None,
    target_group_ids: list[int] | None = None,
    inventory_bindings: dict[str, Any] | None = None,
    provided_variable_names: list[str] | None = None,
) -> PlaybookValidation:
    if binding_profile is not None and (
        binding_profile.playbook_id != revision.playbook_id or binding_profile.user_id != user.id
    ):
        raise PlaybookValidationError("Binding profile does not belong to this user and playbook")

    fingerprint = runtime_fingerprint()
    fingerprint_hash = _hash_payload(fingerprint)
    bindings, servers, outside_bindings = _resolved_validation_context(
        binding_profile,
        user,
        target_server_ids=target_server_ids,
        target_group_ids=target_group_ids,
        inventory_bindings=inventory_bindings,
    )
    target_signature = _target_signature(servers, bindings)
    issues: list[dict[str, Any]] = []
    stages: dict[str, Any] = {
        "input_guard": {"status": "passed", "content_hash": revision.content_hash},
        "bundle": {
            "status": (revision.asset_bundle.scan_status if revision.asset_bundle_id else "not_attached"),
            "bundle_hash": revision.bundle_hash,
        },
    }

    if revision.content_format == "ansible_yaml":
        runtime_bundle = None
        bundle_error = ""
        if revision.asset_bundle_id:
            try:
                runtime_bundle = load_revision_runtime_bundle(revision)
                stages["bundle"]["status"] = "verified"
                stages["bundle"]["entrypoint"] = runtime_bundle.entrypoint if runtime_bundle else ""
            except BundleRuntimeError as exc:
                bundle_error = str(exc)
                stages["bundle"]["status"] = "failed"
        report = compatibility_for_revision(
            revision,
            bindings=bindings,
            target_servers=servers,
        )
        apply_runtime_bundle_evidence(report, runtime_bundle)
        stages["compatibility"] = report
        issues.extend(_enrich_issue(item) for item in report.get("issues") or [])
        if bundle_error:
            issues.append(
                _enrich_issue(
                    {
                        "code": "bundle_integrity_failed",
                        "severity": "error",
                        "message": bundle_error,
                        "path": "bundle",
                    }
                )
            )
        for selector in outside_bindings:
            issues.append(
                _enrich_issue(
                    {
                        "code": "binding_outside_targets",
                        "severity": "error",
                        "message": f"Binding '{selector}' includes servers outside selected targets",
                        "path": "hosts",
                    }
                )
            )
        stages["parse"] = {"status": "failed" if any(item["code"] == "invalid_yaml" for item in issues) else "passed"}
        stages["static_analysis"] = {
            "status": "failed" if any(item["severity"] == "error" for item in issues) else "passed",
            "semantic_hash": report.get("semantic_hash") or "",
            "dependencies": report.get("dependencies") or {},
        }
        stages["bindings"] = {
            "status": "missing" if report.get("missing_bindings") else "complete",
            "missing": report.get("missing_bindings") or [],
        }

        provided_variables = set((binding_profile.variable_values or {}).keys()) if binding_profile else set()
        provided_variables.update((binding_profile.secret_references or {}).keys() if binding_profile else [])
        provided_variables.update(str(name) for name in (provided_variable_names or []) if str(name).strip())
        unresolved = sorted(set(report.get("required_variables") or []) - provided_variables)
        if unresolved:
            issues.append(
                _enrich_issue(
                    {
                        "code": "unresolved_required_variables",
                        "severity": "error",
                        "message": "Required runtime values are missing: " + ", ".join(unresolved[:20]),
                        "path": "vars",
                    }
                )
            )
        stages["variables"] = {"status": "missing" if unresolved else "complete", "missing": unresolved}

        syntax_check = (
            {
                "status": "failed",
                "passed": False,
                "message": bundle_error,
                "method": fingerprint.get("method"),
            }
            if bundle_error
            else validate_playbook_syntax(
                revision.source_yaml,
                allow_dependency_setup=False,
                project_files=runtime_bundle.files if runtime_bundle else None,
                project_entrypoint=runtime_bundle.entrypoint if runtime_bundle else "playbook.yml",
            )
        )
        syntax_check, runtime_mismatch = enforce_runtime_digest_match(
            syntax_check,
            fingerprint,
            message="The Ansible validator runtime changed during validation; retry validation.",
        )
        if runtime_mismatch:
            issues.append(
                _enrich_issue(
                    {
                        "code": "runtime_mismatch",
                        "severity": "error",
                        "message": syntax_check["message"],
                        "path": "runtime",
                        "retryable": True,
                    }
                )
            )
        stages["runtime"] = syntax_check
        readiness = build_execution_readiness(
            report,
            syntax_check=syntax_check,
            targets_count=len(servers),
            requires_runtime=True,
            requires_bindings=True,
        )
    else:
        report = compatibility_for_revision(revision, target_servers=servers)
        stages["compatibility"] = report
        valid_tasks = isinstance(revision.tasks, list) and any(
            isinstance(item, dict) and str(item.get("command") or "").strip() for item in revision.tasks
        )
        if not valid_tasks:
            issues.append(
                _enrich_issue(
                    {
                        "code": "empty_runbook",
                        "severity": "error",
                        "message": "Runbook has no executable tasks",
                    }
                )
            )
        stages["parse"] = {"status": "passed" if valid_tasks else "failed"}
        stages["static_analysis"] = {"status": "passed" if valid_tasks else "failed"}
        stages["bindings"] = {"status": "complete" if servers else "missing", "missing": []}
        stages["variables"] = {"status": "complete", "missing": []}
        stages["runtime"] = {"status": "not_required", "passed": True}
        readiness = build_execution_readiness(
            {"issues": issues, "missing_bindings": []},
            syntax_check=None,
            targets_count=len(servers),
            requires_runtime=False,
            requires_bindings=False,
        )

    stages["targets"] = {
        "status": "ready" if servers else "missing",
        "count": len(servers),
        "signature": target_signature,
    }
    stages["readiness"] = readiness
    has_blockers = any(item["severity"] == "error" for item in issues)
    if has_blockers:
        readiness["execution"] = {"status": "blocked", "ready": False}
    ready = bool(readiness["execution"]["ready"]) and not has_blockers
    status = PlaybookValidation.STATUS_READY if ready else PlaybookValidation.STATUS_BLOCKED

    PlaybookValidation.objects.filter(
        revision=revision,
        status=PlaybookValidation.STATUS_READY,
    ).exclude(
        runtime_fingerprint_hash=fingerprint_hash,
        target_signature=target_signature,
        binding_profile=binding_profile,
        binding_version=binding_profile.version if binding_profile else None,
    ).update(status=PlaybookValidation.STATUS_STALE, stale_reason="Runtime, targets or binding profile changed")

    validation = PlaybookValidation.objects.create(
        revision=revision,
        requested_by=user,
        analyzer_version=str(COMPATIBILITY_ANALYZER_VERSION),
        runtime_fingerprint=fingerprint,
        runtime_fingerprint_hash=fingerprint_hash,
        target_signature=target_signature,
        binding_profile=binding_profile,
        binding_version=binding_profile.version if binding_profile else None,
        status=status,
        stages=stages,
        issues=issues,
        finished_at=timezone.now(),
    )
    record_playbook_event(
        playbook=revision.playbook,
        actor=user,
        event_type="revision_validated",
        entity_type="validation",
        entity_id=validation.id,
        metadata={
            "revision_id": revision.id,
            "status": status,
            "runtime_fingerprint_hash": fingerprint_hash,
            "target_signature": target_signature,
            "binding_profile_id": binding_profile.id if binding_profile else None,
        },
    )
    return validation


def serialize_validation(validation: PlaybookValidation) -> dict[str, Any]:
    stages = validation.stages if isinstance(validation.stages, dict) else {}
    return {
        "id": validation.id,
        "revision_id": validation.revision_id,
        "analyzer_version": validation.analyzer_version,
        "runtime_fingerprint": validation.runtime_fingerprint,
        "runtime_fingerprint_hash": validation.runtime_fingerprint_hash,
        "target_signature": validation.target_signature,
        "binding_profile_id": validation.binding_profile_id,
        "binding_version": validation.binding_version,
        "status": validation.status,
        "stages": stages,
        "compatibility": stages.get("compatibility") or {},
        "issues": validation.issues,
        "stale_reason": validation.stale_reason,
        "started_at": validation.started_at.isoformat(),
        "finished_at": validation.finished_at.isoformat() if validation.finished_at else None,
    }
