"""Single integrity pipeline for creating executable playbook run snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from core_ui.managed_secrets import set_playbook_run_variables
from servers.models import (
    Playbook,
    PlaybookBindingProfile,
    PlaybookRevision,
    PlaybookRun,
    PlaybookValidation,
    Server,
)
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
from servers.services.playbook_runner_support import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    build_inventory_for_servers,
    normalize_tasks,
    resolve_target_servers,
)
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.bindings import resolve_binding_variables
from servers.services.playbooks.bundle_runtime import (
    BundleRuntimeError,
    apply_runtime_bundle_evidence,
    load_revision_runtime_bundle,
)
from servers.services.playbooks.revisions import ensure_playbook_workspace
from servers.services.playbooks.target_identity import target_connection_identity_hashes
from servers.services.playbooks.validation import runtime_fingerprint, validation_is_fresh
from servers.services.playbooks.variables import (
    RuntimeVariableError,
    normalize_runtime_variables,
    variable_manifest,
)


class PlaybookRunPreparationError(ValueError):
    """A controlled blocker found before an immutable run snapshot was created."""

    def __init__(
        self,
        message: str,
        *,
        compatibility: dict[str, Any] | None = None,
        status: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.compatibility = compatibility or {}
        self.status = status


@dataclass(frozen=True)
class PreparedPlaybookRun:
    run: PlaybookRun
    servers: list[Server]


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


def _normalized_engine(raw: Any) -> str:
    engine = str(raw or "ansible").strip().lower()
    return engine if engine in {"auto", "ansible", "shell"} else "ansible"


def _selected_revision(playbook: Playbook, user: Any, data: dict[str, Any]) -> PlaybookRevision:
    published, _draft = ensure_playbook_workspace(playbook, actor=user)
    requested_id = data.get("revision_id")
    if requested_id is None:
        return published
    try:
        revision_id = int(requested_id)
    except (TypeError, ValueError) as exc:
        raise PlaybookRunPreparationError("revision_id must be an integer") from exc
    revision = PlaybookRevision.objects.filter(playbook=playbook, id=revision_id).first()
    if revision is None:
        raise PlaybookRunPreparationError("Playbook revision not found", status=404)
    capabilities = capabilities_for(playbook, user)
    if revision.id != playbook.published_revision_id and not capabilities.is_owner:
        raise PlaybookRunPreparationError("Only the published revision can be run", status=403)
    return revision


def _binding_profile(playbook: Playbook, user: Any, data: dict[str, Any]) -> PlaybookBindingProfile | None:
    requested_id = data.get("binding_profile_id")
    profiles = PlaybookBindingProfile.objects.filter(playbook=playbook, user=user)
    if requested_id is None:
        return profiles.filter(is_default=True).first()
    try:
        profile_id = int(requested_id)
    except (TypeError, ValueError) as exc:
        raise PlaybookRunPreparationError("binding_profile_id must be an integer") from exc
    profile = profiles.filter(id=profile_id).first()
    if profile is None:
        raise PlaybookRunPreparationError("Binding profile not found", status=404)
    return profile


def _readiness_report(
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


def _raise_blocker(message: str, report: dict[str, Any]) -> None:
    raise PlaybookRunPreparationError(message, compatibility=report)


def prepare_playbook_run(
    *,
    user: Any,
    playbook: Playbook,
    payload: dict[str, Any] | None,
    syntax_validator: Callable[[str], dict[str, Any]] | None = None,
    enqueue_master_password: str | None = None,
) -> PreparedPlaybookRun:
    """Authorize, validate and persist one immutable execution snapshot.

    HTTP, Operator and future launch surfaces must call this service before
    dispatching ``run.id``. Passing ``enqueue_master_password`` atomically
    creates the durable dispatch; no execution is started in this process.
    """

    data = payload if isinstance(payload, dict) else {}
    capabilities = capabilities_for(playbook, user)
    if not capabilities.can_run:
        raise PlaybookRunPreparationError("You do not have permission to run this playbook", status=403)

    selected_revision = _selected_revision(playbook, user, data)
    playbook.refresh_from_db(fields=["origin_revision", "published_revision"])
    binding_profile = _binding_profile(playbook, user, data)
    server_ids = _integer_ids(data.get("server_ids"))
    group_ids = _integer_ids(data.get("group_ids"))
    if not server_ids and not group_ids and binding_profile is not None:
        mappings = normalize_inventory_bindings(binding_profile.selector_mappings)
        server_ids = sorted(
            {server_id for binding in mappings.values() for server_id in binding.get("server_ids") or []}
        )
        group_ids = sorted({group_id for binding in mappings.values() for group_id in binding.get("group_ids") or []})
    servers = resolve_target_servers(user, server_ids=server_ids, group_ids=group_ids)
    if not servers:
        report = _readiness_report(
            {},
            syntax_check=None,
            targets_count=0,
            requires_runtime=False,
            requires_bindings=False,
        )
        _raise_blocker("Select at least one accessible server or group", report)

    tasks = normalize_tasks(selected_revision.tasks)
    revision_source_yaml = selected_revision.source_yaml or ""
    source_yaml = revision_source_yaml
    origin = playbook.origin_revision
    original_source_yaml = (
        ((origin.source_yaml if origin else playbook.source_yaml) or "") if capabilities.is_owner else ""
    )
    legacy_compatibility_id = (selected_revision.metadata or {}).get("legacy_compatibility_revision_id")
    legacy_compatibility = None
    if legacy_compatibility_id:
        candidate = playbook.active_compatibility_revision
        legacy_compatibility = (
            candidate
            if candidate is not None and candidate.id == legacy_compatibility_id
            else playbook.compatibility_revisions.filter(id=legacy_compatibility_id).first()
        )
    if not tasks and not source_yaml.strip():
        raise PlaybookRunPreparationError("Playbook has no tasks or Ansible YAML")

    try:
        runtime_variables = resolve_binding_variables(binding_profile) if binding_profile else {}
        runtime_variables.update(normalize_runtime_variables(data.get("extra_vars")))
    except RuntimeVariableError as exc:
        raise PlaybookRunPreparationError(str(exc)) from exc
    variables_manifest = variable_manifest(runtime_variables, binding_profile=binding_profile)

    engine = _normalized_engine(data.get("engine"))
    inventory_binding_groups: dict[str, list[int]] = {}
    normalized_bindings: dict[str, dict[str, list[int]]] = {}
    compatibility_report: dict[str, Any] = {}
    runtime_bundle = None

    if source_yaml:
        if engine == "shell":
            report = _readiness_report(
                {"issues": []},
                syntax_check=None,
                targets_count=len(servers),
            )
            _raise_blocker("Ansible YAML can only run with the Ansible engine", report)
        # ``auto`` may select an engine for command runbooks, but Ansible source
        # is never a candidate for the lossy shell projection.
        engine = "ansible"
        if selected_revision.asset_bundle_id:
            try:
                runtime_bundle = load_revision_runtime_bundle(selected_revision)
            except BundleRuntimeError as exc:
                report = _readiness_report(
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
                    targets_count=len(servers),
                )
                _raise_blocker(str(exc), report)
        raw_bindings = (
            data.get("inventory_bindings")
            if "inventory_bindings" in data
            else binding_profile.selector_mappings
            if binding_profile is not None
            else legacy_compatibility.inventory_bindings
            if legacy_compatibility is not None
            else {}
        )
        normalized_bindings = normalize_inventory_bindings(raw_bindings)
        resolved_bindings: dict[str, list[int]] = {}
        selected_ids = {server.id for server in servers}
        for selector, binding in normalized_bindings.items():
            bound_servers = resolve_target_servers(
                user,
                server_ids=binding["server_ids"],
                group_ids=binding["group_ids"],
            )
            bound_ids = sorted({server.id for server in bound_servers})
            if not set(bound_ids).issubset(selected_ids):
                report = _readiness_report(
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
                _raise_blocker(f"Binding '{selector}' includes servers outside selected targets", report)
            resolved_bindings[selector] = bound_ids

        analysis_bindings = {
            selector: {"server_ids": ids, "group_ids": []} for selector, ids in resolved_bindings.items()
        }
        compatibility_report = analyze_playbook_compatibility(
            source_yaml,
            bindings=analysis_bindings,
            target_servers=servers,
        )
        apply_runtime_bundle_evidence(compatibility_report, runtime_bundle)
        _readiness_report(
            compatibility_report,
            syntax_check=None,
            targets_count=len(servers),
        )
        blockers = [item for item in compatibility_report.get("issues") or [] if item.get("severity") == "error"]
        if blockers:
            _raise_blocker(
                blockers[0].get("message") or "Playbook compatibility check failed",
                compatibility_report,
            )
        if compatibility_report.get("missing_bindings"):
            _raise_blocker("Map every playbook host selector before running", compatibility_report)

        missing_variables = sorted(set(compatibility_report.get("required_variables") or []) - set(runtime_variables))
        if missing_variables:
            compatibility_report.setdefault("issues", []).append(
                {
                    "code": "unresolved_required_variables",
                    "severity": "error",
                    "message": "Required runtime values are missing: " + ", ".join(missing_variables[:20]),
                    "path": "vars",
                }
            )
            _readiness_report(
                compatibility_report,
                syntax_check=None,
                targets_count=len(servers),
            )
            compatibility_report["readiness"]["execution"] = {"status": "blocked", "ready": False}
            _raise_blocker("Provide every required runtime variable before running", compatibility_report)

        try:
            source_yaml, inventory_binding_groups = compile_runtime_playbook_yaml(source_yaml, resolved_bindings)
        except ValueError as exc:
            _raise_blocker(str(exc), compatibility_report)

        validation = None
        execution_fingerprint: dict[str, Any] = {}
        if data.get("validation_id") is not None:
            try:
                validation_id = int(data["validation_id"])
            except (TypeError, ValueError) as exc:
                raise PlaybookRunPreparationError("validation_id must be an integer") from exc
            validation = PlaybookValidation.objects.filter(
                id=validation_id,
                revision=selected_revision,
                requested_by=user,
            ).first()
            if validation is None:
                raise PlaybookRunPreparationError("Validation evidence not found", status=404)
            execution_fingerprint = runtime_fingerprint()
            fresh, stale_reason = validation_is_fresh(
                validation,
                revision=selected_revision,
                binding_profile=binding_profile,
                servers=servers,
                inventory_bindings=analysis_bindings,
                fingerprint=execution_fingerprint,
            )
            if not fresh:
                validation.status = PlaybookValidation.STATUS_STALE
                validation.stale_reason = stale_reason
                validation.save(update_fields=["status", "stale_reason"])
                compatibility_report["validation"] = {
                    "id": validation.id,
                    "status": validation.status,
                    "stale_reason": stale_reason,
                }
                _raise_blocker(
                    "Validation is stale; validate this revision and target profile again", compatibility_report
                )
            syntax_check = validation.stages.get("runtime") if isinstance(validation.stages, dict) else {}
        else:
            execution_fingerprint = runtime_fingerprint()
            syntax_check = (
                syntax_validator(source_yaml)
                if syntax_validator is not None
                else (
                    validate_playbook_syntax(
                        source_yaml,
                        project_files=runtime_bundle.files,
                        project_entrypoint=runtime_bundle.entrypoint,
                    )
                    if runtime_bundle
                    else validate_playbook_syntax(source_yaml)
                )
            )
            execution_fingerprint.update(mode="live_preflight", syntax_status=syntax_check.get("status") or "")
            syntax_check, _runtime_mismatch = enforce_runtime_digest_match(
                syntax_check, execution_fingerprint, message="The Ansible validator runtime changed; retry preflight."
            )
        compatibility_report["syntax_check"] = syntax_check
        _readiness_report(
            compatibility_report,
            syntax_check=syntax_check,
            targets_count=len(servers),
        )
        if syntax_check.get("passed") is not True:
            _raise_blocker(
                syntax_check.get("message") or "Ansible runtime syntax check did not pass",
                compatibility_report,
            )
    else:
        validation = None
        execution_fingerprint = {"mode": "runbook", "runtime": "not_required"}
        compatibility_report = _readiness_report(
            {},
            syntax_check=None,
            targets_count=len(servers),
            requires_runtime=False,
            requires_bindings=False,
        )

    try:
        concurrency = int(data.get("concurrency") or DEFAULT_CONCURRENCY)
    except (TypeError, ValueError):
        concurrency = DEFAULT_CONCURRENCY
    concurrency = max(1, min(concurrency, MAX_CONCURRENCY))
    dry_run = bool(data.get("dry_run") or data.get("check_mode"))
    options = {
        "concurrency": concurrency,
        "dry_run": dry_run,
        "engine": engine,
        "become": bool(data.get("become", True)),
        "tags": str(data.get("tags") or "")[:500],
        "skip_tags": str(data.get("skip_tags") or "")[:500],
        "limit": str(data.get("limit") or "")[:500],
        "inventory_binding_groups": inventory_binding_groups,
    }
    target_connection_identities = target_connection_identity_hashes(servers)
    snapshot = {
        "id": playbook.id,
        "name": playbook.name,
        "description": playbook.description,
        "kind": playbook.kind,
        "category": playbook.category,
        "revision_id": selected_revision.id,
        "revision_number": selected_revision.revision_number,
        "revision_content_hash": selected_revision.content_hash,
        "bundle_hash": selected_revision.bundle_hash,
        "asset_bundle_id": selected_revision.asset_bundle_id,
        "project_entrypoint": runtime_bundle.entrypoint if runtime_bundle else "",
        "source_yaml": source_yaml,
        "revision_source_yaml": revision_source_yaml,
        "source_yaml_original": original_source_yaml,
        "compatibility_revision_id": legacy_compatibility.id if legacy_compatibility else None,
        "validation_id": validation.id if validation else None,
        "runtime_fingerprint": execution_fingerprint,
        "binding_profile_id": binding_profile.id if binding_profile else None,
        "binding_version": binding_profile.version if binding_profile else None,
        "binding_hash": binding_profile.content_hash if binding_profile else "",
        "compatibility": compatibility_report,
        "inventory_bindings": normalized_bindings,
        "target_connection_identities": target_connection_identities,
        "tasks": [
            {
                "id": task["id"],
                "command": task["command"],
                "description": task.get("description") or "",
                "continue_on_error": bool(task.get("continue_on_error")),
            }
            for task in tasks
        ],
    }

    with transaction.atomic():
        run = PlaybookRun.objects.create(
            playbook=playbook,
            user=user,
            revision=selected_revision,
            validation=validation,
            binding_profile=binding_profile,
            status=PlaybookRun.STATUS_PENDING,
            playbook_snapshot=snapshot,
            target_server_ids=[server.id for server in servers],
            target_group_ids=group_ids,
            options=options,
            variable_manifest=variables_manifest,
            execution_fingerprint=execution_fingerprint,
            host_results=[],
            summary={},
            inventory_preview=build_inventory_for_servers(
                servers,
                extra_groups=inventory_binding_groups,
            ),
        )
        set_playbook_run_variables(run.id, runtime_variables)
        if enqueue_master_password is not None:
            from servers.playbook_dispatch import enqueue_playbook_run_dispatch

            enqueue_playbook_run_dispatch(
                run=run,
                master_password=enqueue_master_password,
            )
    return PreparedPlaybookRun(run=run, servers=servers)
