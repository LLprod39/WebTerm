"""Ansible-specific stage of immutable playbook run preparation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from servers.models_inventory import Server
from servers.models_playbook_workspace import PlaybookBindingProfile, PlaybookRevision, PlaybookValidation
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility
from servers.services.playbook_compatibility_inventory import (
    compile_runtime_playbook_yaml,
    normalize_inventory_bindings,
)
from servers.services.playbook_compatibility_validation import (
    build_execution_readiness,
    enforce_runtime_digest_match,
    validate_playbook_syntax,
)
from servers.services.playbook_runner_support import resolve_target_servers
from servers.services.playbooks.bundle_runtime import (
    BundleRuntimeError,
    RuntimeProjectBundle,
    apply_runtime_bundle_evidence,
    load_revision_runtime_bundle,
)
from servers.services.playbooks.validation import runtime_fingerprint, validation_is_fresh


class AnsibleRunPreparationError(ValueError):
    def __init__(self, message: str, *, report: dict[str, Any] | None = None, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.report = report or {}
        self.status = status


@dataclass(frozen=True)
class PreparedAnsibleExecution:
    source_yaml: str
    engine: str
    inventory_binding_groups: dict[str, list[int]]
    normalized_bindings: dict[str, dict[str, list[int]]]
    compatibility_report: dict[str, Any]
    runtime_bundle: RuntimeProjectBundle | None
    validation: PlaybookValidation | None
    execution_fingerprint: dict[str, Any]


def readiness_report(
    report: dict[str, Any],
    *,
    syntax_check: dict[str, Any] | None,
    targets_count: int,
    requires_runtime: bool = True,
    requires_bindings: bool = True,
) -> dict[str, Any]:
    report["readiness"] = build_execution_readiness(
        report,
        syntax_check=syntax_check,
        targets_count=targets_count,
        requires_runtime=requires_runtime,
        requires_bindings=requires_bindings,
    )
    report["execution_ready"] = report["readiness"]["execution"]["ready"]
    return report


def resolve_preparation_targets(
    *,
    user: Any,
    data: dict[str, Any],
    binding_profile: PlaybookBindingProfile | None,
) -> tuple[list[Server], list[int]]:
    server_ids = _integer_ids(data.get("server_ids"))
    group_ids = _integer_ids(data.get("group_ids"))
    if not server_ids and not group_ids and binding_profile is not None:
        mappings = normalize_inventory_bindings(binding_profile.selector_mappings)
        server_ids = sorted(
            {server_id for binding in mappings.values() for server_id in binding.get("server_ids") or []}
        )
        group_ids = sorted(
            {group_id for binding in mappings.values() for group_id in binding.get("group_ids") or []}
        )
    servers = resolve_target_servers(user, server_ids=server_ids, group_ids=group_ids)
    if not servers:
        report = readiness_report(
            {},
            syntax_check=None,
            targets_count=0,
            requires_runtime=False,
            requires_bindings=False,
        )
        _block("Select at least one accessible server or group", report)
    return servers, group_ids


def prepare_ansible_execution(
    *,
    user: Any,
    revision: PlaybookRevision,
    source_yaml: str,
    requested_engine: str,
    data: dict[str, Any],
    binding_profile: PlaybookBindingProfile | None,
    legacy_compatibility: Any,
    servers: list[Server],
    runtime_variables: dict[str, Any],
    syntax_validator: Callable[[str], dict[str, Any]] | None,
) -> PreparedAnsibleExecution:
    if requested_engine == "shell":
        _block(
            "Ansible YAML can only run with the Ansible engine",
            readiness_report({"issues": []}, syntax_check=None, targets_count=len(servers)),
        )
    runtime_bundle = _load_runtime_bundle(revision, targets_count=len(servers))
    normalized, resolved = _resolve_bindings(
        user=user,
        data=data,
        binding_profile=binding_profile,
        legacy_compatibility=legacy_compatibility,
        servers=servers,
    )
    analysis_bindings = {selector: {"server_ids": ids, "group_ids": []} for selector, ids in resolved.items()}
    report = _compatibility_report(
        source_yaml=source_yaml,
        analysis_bindings=analysis_bindings,
        servers=servers,
        runtime_bundle=runtime_bundle,
        runtime_variables=runtime_variables,
    )
    try:
        runtime_source, inventory_groups = compile_runtime_playbook_yaml(source_yaml, resolved)
    except ValueError as exc:
        _block(str(exc), report)
    validation, fingerprint, syntax_check = _validation_evidence(
        user=user,
        revision=revision,
        source_yaml=runtime_source,
        data=data,
        binding_profile=binding_profile,
        servers=servers,
        analysis_bindings=analysis_bindings,
        runtime_bundle=runtime_bundle,
        syntax_validator=syntax_validator,
        report=report,
    )
    report["syntax_check"] = syntax_check
    readiness_report(report, syntax_check=syntax_check, targets_count=len(servers))
    if syntax_check.get("passed") is not True:
        _block(syntax_check.get("message") or "Ansible runtime syntax check did not pass", report)
    return PreparedAnsibleExecution(
        source_yaml=runtime_source,
        engine="ansible",
        inventory_binding_groups=inventory_groups,
        normalized_bindings=normalized,
        compatibility_report=report,
        runtime_bundle=runtime_bundle,
        validation=validation,
        execution_fingerprint=fingerprint,
    )


def _load_runtime_bundle(revision: PlaybookRevision, *, targets_count: int) -> RuntimeProjectBundle | None:
    if not revision.asset_bundle_id:
        return None
    try:
        return load_revision_runtime_bundle(revision)
    except BundleRuntimeError as exc:
        report = readiness_report(
            {
                "issues": [
                    {
                        "code": "bundle_integrity_failed",
                        "severity": "error",
                        "message": str(exc),
                        "path": "bundle",
                    }
                ]
            },
            syntax_check=None,
            targets_count=targets_count,
        )
        _block(str(exc), report)


def _resolve_bindings(
    *,
    user: Any,
    data: dict[str, Any],
    binding_profile: PlaybookBindingProfile | None,
    legacy_compatibility: Any,
    servers: list[Server],
) -> tuple[dict[str, dict[str, list[int]]], dict[str, list[int]]]:
    raw_bindings = (
        data.get("inventory_bindings")
        if "inventory_bindings" in data
        else binding_profile.selector_mappings
        if binding_profile is not None
        else legacy_compatibility.inventory_bindings
        if legacy_compatibility is not None
        else {}
    )
    normalized = normalize_inventory_bindings(raw_bindings)
    selected_ids = {server.id for server in servers}
    resolved: dict[str, list[int]] = {}
    for selector, binding in normalized.items():
        bound_servers = resolve_target_servers(
            user,
            server_ids=binding["server_ids"],
            group_ids=binding["group_ids"],
        )
        bound_ids = sorted({server.id for server in bound_servers})
        if not set(bound_ids).issubset(selected_ids):
            report = readiness_report(
                {
                    "issues": [
                        {
                            "code": "binding_outside_targets",
                            "severity": "error",
                            "message": f"Binding '{selector}' includes servers outside selected targets",
                            "path": "hosts",
                        }
                    ]
                },
                syntax_check=None,
                targets_count=len(servers),
            )
            _block(f"Binding '{selector}' includes servers outside selected targets", report)
        resolved[selector] = bound_ids
    return normalized, resolved


def _compatibility_report(
    *,
    source_yaml: str,
    analysis_bindings: dict[str, Any],
    servers: list[Server],
    runtime_bundle: RuntimeProjectBundle | None,
    runtime_variables: dict[str, Any],
) -> dict[str, Any]:
    report = analyze_playbook_compatibility(source_yaml, bindings=analysis_bindings, target_servers=servers)
    apply_runtime_bundle_evidence(report, runtime_bundle)
    readiness_report(report, syntax_check=None, targets_count=len(servers))
    blockers = [item for item in report.get("issues") or [] if item.get("severity") == "error"]
    if blockers:
        _block(blockers[0].get("message") or "Playbook compatibility check failed", report)
    if report.get("missing_bindings"):
        _block("Map every playbook host selector before running", report)
    missing_variables = sorted(set(report.get("required_variables") or []) - set(runtime_variables))
    if missing_variables:
        report.setdefault("issues", []).append(
            {
                "code": "unresolved_required_variables",
                "severity": "error",
                "message": "Required runtime values are missing: " + ", ".join(missing_variables[:20]),
                "path": "vars",
            }
        )
        readiness_report(report, syntax_check=None, targets_count=len(servers))
        report["readiness"]["execution"] = {"status": "blocked", "ready": False}
        _block("Provide every required runtime variable before running", report)
    return report


def _validation_evidence(
    *,
    user: Any,
    revision: PlaybookRevision,
    source_yaml: str,
    data: dict[str, Any],
    binding_profile: PlaybookBindingProfile | None,
    servers: list[Server],
    analysis_bindings: dict[str, Any],
    runtime_bundle: RuntimeProjectBundle | None,
    syntax_validator: Callable[[str], dict[str, Any]] | None,
    report: dict[str, Any],
) -> tuple[PlaybookValidation | None, dict[str, Any], dict[str, Any]]:
    if data.get("validation_id") is None:
        fingerprint = runtime_fingerprint()
        syntax_check = _live_syntax_check(source_yaml, runtime_bundle, syntax_validator)
        fingerprint.update(mode="live_preflight", syntax_status=syntax_check.get("status") or "")
        syntax_check, _runtime_mismatch = enforce_runtime_digest_match(
            syntax_check,
            fingerprint,
            message="The Ansible validator runtime changed; retry preflight.",
        )
        return None, fingerprint, syntax_check
    try:
        validation_id = int(data["validation_id"])
    except (TypeError, ValueError) as exc:
        raise AnsibleRunPreparationError("validation_id must be an integer") from exc
    validation = PlaybookValidation.objects.filter(
        id=validation_id,
        revision=revision,
        requested_by=user,
    ).first()
    if validation is None:
        raise AnsibleRunPreparationError("Validation evidence not found", status=404)
    fingerprint = runtime_fingerprint()
    fresh, stale_reason = validation_is_fresh(
        validation,
        revision=revision,
        binding_profile=binding_profile,
        servers=servers,
        inventory_bindings=analysis_bindings,
        fingerprint=fingerprint,
    )
    if not fresh:
        validation.status = PlaybookValidation.STATUS_STALE
        validation.stale_reason = stale_reason
        validation.save(update_fields=["status", "stale_reason"])
        report["validation"] = {"id": validation.id, "status": validation.status, "stale_reason": stale_reason}
        _block("Validation is stale; validate this revision and target profile again", report)
    syntax_check = validation.stages.get("runtime") if isinstance(validation.stages, dict) else {}
    return validation, fingerprint, syntax_check


def _live_syntax_check(
    source_yaml: str,
    runtime_bundle: RuntimeProjectBundle | None,
    syntax_validator: Callable[[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    if syntax_validator is not None:
        return syntax_validator(source_yaml)
    if runtime_bundle:
        return validate_playbook_syntax(
            source_yaml,
            project_files=runtime_bundle.files,
            project_entrypoint=runtime_bundle.entrypoint,
        )
    return validate_playbook_syntax(source_yaml)


def _block(message: str, report: dict[str, Any]) -> None:
    raise AnsibleRunPreparationError(message, report=report)


def _integer_ids(raw: Any) -> list[int]:
    values = raw if isinstance(raw, list) else []
    ids: set[int] = set()
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            ids.add(parsed)
    return sorted(ids)
