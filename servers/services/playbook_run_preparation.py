"""Single integrity pipeline for creating executable playbook run snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from core_ui.managed_secrets import set_playbook_run_variables
from servers.models_inventory import Server
from servers.models_playbook_workspace import PlaybookBindingProfile, PlaybookRevision
from servers.models_playbooks import Playbook, PlaybookRun
from servers.services.playbook_compatibility_validation import validate_playbook_syntax
from servers.services.playbook_run_preparation_ansible import (
    AnsibleRunPreparationError,
    PreparedAnsibleExecution,
    prepare_ansible_execution,
    resolve_preparation_targets,
)
from servers.services.playbook_run_preparation_ansible import (
    readiness_report as _readiness_report,
)
from servers.services.playbook_runner_support import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    build_inventory_for_servers,
    normalize_tasks,
)
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.bindings import resolve_binding_variables
from servers.services.playbooks.bundle_archive import BundleValidationError
from servers.services.playbooks.revision_safety import validate_revision_safety
from servers.services.playbooks.revisions import ensure_playbook_workspace
from servers.services.playbooks.target_identity import target_connection_identity_hashes
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


def _raise_blocker(message: str, report: dict[str, Any]) -> None:
    raise PlaybookRunPreparationError(message, compatibility=report)


def _safe_selected_revision(playbook: Playbook, user: Any, data: dict[str, Any]) -> PlaybookRevision:
    try:
        revision = _selected_revision(playbook, user, data)
        validate_revision_safety(revision)
        return revision
    except BundleValidationError as exc:
        raise PlaybookRunPreparationError(
            "Selected playbook revision failed safety validation",
            compatibility={
                "issues": [
                    {
                        "code": exc.code,
                        "severity": "error",
                        "message": "Selected playbook revision failed safety validation",
                        "path": "revision",
                    }
                ]
            },
            status=422,
        ) from exc


def _legacy_compatibility(playbook: Playbook, revision: PlaybookRevision):
    compatibility_id = (revision.metadata or {}).get("legacy_compatibility_revision_id")
    if not compatibility_id:
        return None
    candidate = playbook.active_compatibility_revision
    if candidate is not None and candidate.id == compatibility_id:
        return candidate
    return playbook.compatibility_revisions.filter(id=compatibility_id).first()


def _runtime_variable_context(data: dict[str, Any], binding_profile):
    try:
        values = resolve_binding_variables(binding_profile) if binding_profile else {}
        values.update(normalize_runtime_variables(data.get("extra_vars")))
    except RuntimeVariableError as exc:
        raise PlaybookRunPreparationError(str(exc)) from exc
    return values, variable_manifest(values, binding_profile=binding_profile)


def _runbook_runtime(engine: str, *, targets_count: int) -> PreparedAnsibleExecution:
    return PreparedAnsibleExecution(
        source_yaml="",
        engine=engine,
        inventory_binding_groups={},
        normalized_bindings={},
        compatibility_report=_readiness_report(
            {},
            syntax_check=None,
            targets_count=targets_count,
            requires_runtime=False,
            requires_bindings=False,
        ),
        runtime_bundle=None,
        validation=None,
        execution_fingerprint={"mode": "runbook", "runtime": "not_required"},
    )


def _run_options(data: dict[str, Any], runtime: PreparedAnsibleExecution) -> dict[str, Any]:
    try:
        concurrency = int(data.get("concurrency") or DEFAULT_CONCURRENCY)
    except (TypeError, ValueError):
        concurrency = DEFAULT_CONCURRENCY
    return {
        "concurrency": max(1, min(concurrency, MAX_CONCURRENCY)),
        "dry_run": bool(data.get("dry_run") or data.get("check_mode")),
        "engine": runtime.engine,
        "become": bool(data.get("become", True)),
        "tags": str(data.get("tags") or "")[:500],
        "skip_tags": str(data.get("skip_tags") or "")[:500],
        "limit": str(data.get("limit") or "")[:500],
        "inventory_binding_groups": runtime.inventory_binding_groups,
    }


def _playbook_snapshot(
    *,
    playbook: Playbook,
    revision: PlaybookRevision,
    binding_profile,
    runtime: PreparedAnsibleExecution,
    revision_source_yaml: str,
    original_source_yaml: str,
    legacy_compatibility,
    servers: list[Server],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime_bundle = runtime.runtime_bundle
    return {
        "id": playbook.id,
        "name": playbook.name,
        "description": playbook.description,
        "kind": playbook.kind,
        "category": playbook.category,
        "revision_id": revision.id,
        "revision_number": revision.revision_number,
        "revision_content_hash": revision.content_hash,
        "bundle_hash": revision.bundle_hash,
        "asset_bundle_id": revision.asset_bundle_id,
        "project_entrypoint": runtime_bundle.entrypoint if runtime_bundle else "",
        "source_yaml": runtime.source_yaml,
        "revision_source_yaml": revision_source_yaml,
        "source_yaml_original": original_source_yaml,
        "compatibility_revision_id": legacy_compatibility.id if legacy_compatibility else None,
        "validation_id": runtime.validation.id if runtime.validation else None,
        "runtime_fingerprint": runtime.execution_fingerprint,
        "binding_profile_id": binding_profile.id if binding_profile else None,
        "binding_version": binding_profile.version if binding_profile else None,
        "binding_hash": binding_profile.content_hash if binding_profile else "",
        "compatibility": runtime.compatibility_report,
        "inventory_bindings": runtime.normalized_bindings,
        "target_connection_identities": target_connection_identity_hashes(servers),
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


def _persist_prepared_run(
    *,
    playbook: Playbook,
    user: Any,
    revision: PlaybookRevision,
    binding_profile,
    servers: list[Server],
    group_ids: list[int],
    options: dict[str, Any],
    variables_manifest: dict[str, Any],
    runtime_variables: dict[str, Any],
    runtime: PreparedAnsibleExecution,
    snapshot: dict[str, Any],
    enqueue_master_password: str | None,
) -> PlaybookRun:
    with transaction.atomic():
        run = PlaybookRun.objects.create(
            playbook=playbook,
            user=user,
            revision=revision,
            validation=runtime.validation,
            binding_profile=binding_profile,
            status=PlaybookRun.STATUS_PENDING,
            playbook_snapshot=snapshot,
            target_server_ids=[server.id for server in servers],
            target_group_ids=group_ids,
            options=options,
            variable_manifest=variables_manifest,
            execution_fingerprint=runtime.execution_fingerprint,
            host_results=[],
            summary={},
            inventory_preview=build_inventory_for_servers(
                servers,
                extra_groups=runtime.inventory_binding_groups,
            ),
        )
        set_playbook_run_variables(run.id, runtime_variables)
        if enqueue_master_password is not None:
            from servers.playbooks.dispatch import enqueue_playbook_run_dispatch

            enqueue_playbook_run_dispatch(run=run, master_password=enqueue_master_password)
    return run


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

    selected_revision = _safe_selected_revision(playbook, user, data)
    playbook.refresh_from_db(fields=["origin_revision", "published_revision"])
    binding_profile = _binding_profile(playbook, user, data)
    try:
        servers, group_ids = resolve_preparation_targets(
            user=user,
            data=data,
            binding_profile=binding_profile,
        )
    except AnsibleRunPreparationError as exc:
        raise PlaybookRunPreparationError(
            exc.message,
            compatibility=exc.report,
            status=exc.status,
        ) from exc

    tasks = normalize_tasks(selected_revision.tasks)
    revision_source_yaml = selected_revision.source_yaml or ""
    origin = playbook.origin_revision
    original_source_yaml = (
        ((origin.source_yaml if origin else playbook.source_yaml) or "") if capabilities.is_owner else ""
    )
    legacy_compatibility = _legacy_compatibility(playbook, selected_revision)
    if not tasks and not revision_source_yaml.strip():
        raise PlaybookRunPreparationError("Playbook has no tasks or Ansible YAML")
    runtime_variables, variables_manifest = _runtime_variable_context(data, binding_profile)
    engine = _normalized_engine(data.get("engine"))

    try:
        runtime = (
            prepare_ansible_execution(
                user=user,
                revision=selected_revision,
                source_yaml=revision_source_yaml,
                requested_engine=engine,
                data=data,
                binding_profile=binding_profile,
                legacy_compatibility=legacy_compatibility,
                servers=servers,
                runtime_variables=runtime_variables,
                syntax_validator=syntax_validator or validate_playbook_syntax,
            )
            if revision_source_yaml
            else _runbook_runtime(engine, targets_count=len(servers))
        )
    except AnsibleRunPreparationError as exc:
        raise PlaybookRunPreparationError(
            exc.message,
            compatibility=exc.report,
            status=exc.status,
        ) from exc

    options = _run_options(data, runtime)
    snapshot = _playbook_snapshot(
        playbook=playbook,
        revision=selected_revision,
        binding_profile=binding_profile,
        runtime=runtime,
        revision_source_yaml=revision_source_yaml,
        original_source_yaml=original_source_yaml,
        legacy_compatibility=legacy_compatibility,
        servers=servers,
        tasks=tasks,
    )
    run = _persist_prepared_run(
        playbook=playbook,
        user=user,
        revision=selected_revision,
        binding_profile=binding_profile,
        servers=servers,
        group_ids=group_ids,
        options=options,
        variables_manifest=variables_manifest,
        runtime_variables=runtime_variables,
        runtime=runtime,
        snapshot=snapshot,
        enqueue_master_password=enqueue_master_password,
    )
    return PreparedPlaybookRun(run=run, servers=servers)
