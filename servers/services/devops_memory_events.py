"""Normalized, redacted DevOps event envelopes for server memory ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from django.conf import settings

from app.egress_redaction import redact_for_storage
from servers.models import (
    AgentRun,
    PlaybookRun,
    Server,
    ServerAlert,
    ServerCommandHistory,
    ServerHealthCheck,
    ServerWatcherDraft,
)
from studio.models import PipelineRun

FEATURE_FLAG_SETTING = "SERVER_MEMORY_DEVOPS_EVENTS_ENABLED"
SCHEMA_VERSION = "devops_event.v1"
MAX_EXCERPT_BYTES = 1024
MAX_SUMMARY_BYTES = 512
MAX_CONTRACT_BYTES = 12_000
MAX_EVIDENCE_REFS = 12
_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")


class DevOpsMemoryEventError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def devops_memory_events_enabled() -> bool:
    return bool(getattr(settings, FEATURE_FLAG_SETTING, False))


def enqueue_devops_memory_event(
    *,
    server: Server,
    source: Any,
    event_family: str,
    transition: str,
    redacted_excerpt: str = "",
    verification_summary: str = "",
    rollback_summary: str = "",
    environment_ref: str = "",
    service_ref: str = "",
    evidence_refs: list[str] | None = None,
) -> str | None:
    """Validate a source relationship and enqueue one normalized event.

    The disabled path returns before inspecting source data or touching the queue.
    """
    if not devops_memory_events_enabled():
        return None
    server = Server.objects.filter(pk=getattr(server, "pk", None)).first()
    if server is None:
        raise DevOpsMemoryEventError("A persisted server is required", code="server_invalid")
    source = _load_persisted_source(source)
    family = _bounded_token(event_family, field="event_family")
    transition_token = _bounded_token(transition, field="transition")
    environment = _bounded_ref(environment_ref, field="environment_ref", allow_blank=True)
    service = _bounded_ref(service_ref, field="service_ref", allow_blank=True)
    excerpt = _redacted_bounded_text(redacted_excerpt, limit=MAX_EXCERPT_BYTES, field="redacted_excerpt")
    verification = _summary_envelope(verification_summary, field="verification_summary")
    rollback = _summary_envelope(rollback_summary, field="rollback_summary")

    source_contract = _source_contract(server=server, source=source, event_family=family)
    authorized_refs = _authorized_evidence_refs(server=server, source=source, source_contract=source_contract)
    requested_refs = [_bounded_ref(value, field="evidence_ref") for value in (evidence_refs or [])]
    if len(requested_refs) > MAX_EVIDENCE_REFS or any(value not in authorized_refs for value in requested_refs):
        raise DevOpsMemoryEventError("Evidence references are outside the source scope", code="evidence_ref_invalid")
    bounded_evidence = list(dict.fromkeys([*authorized_refs, *requested_refs]))[:MAX_EVIDENCE_REFS]

    idempotency_digest = _idempotency_digest(
        server_id=server.id,
        object_type=source_contract["object_type"],
        object_id=source_contract["id"],
        transition=transition_token,
        outcome=source_contract["outcome"],
        version=source_contract["version"],
    )
    idempotency_key = f"devops:v1:{idempotency_digest}"
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_family": family,
        "transition": transition_token,
        "source": source_contract,
        "refs": {
            "server": f"server:{server.id}",
            "project": f"project:{server.project_id}",
            "environment": environment,
            "service": service,
        },
        "timestamps": {
            "observed_at": source_contract["observed_at"],
            "started_at": source_contract["started_at"],
            "resolved_at": source_contract["resolved_at"],
        },
        "outcome": source_contract["outcome"],
        "evidence_refs": bounded_evidence,
        "redacted_excerpt": excerpt,
        "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "verification": verification,
        "rollback": rollback,
    }
    if isinstance(source_contract.get("exit_code"), int):
        payload["exit_code"] = source_contract["exit_code"]
    contract_bytes = _canonical_json(payload)
    if len(contract_bytes) > MAX_CONTRACT_BYTES:
        raise DevOpsMemoryEventError("DevOps event contract is too large", code="contract_too_large")
    event_metadata = {
        "devops_event": {
            "schema_version": SCHEMA_VERSION,
            "event_family": family,
            "source_object_type": source_contract["object_type"],
            "source_object_id": source_contract["id"],
            "source_state": source_contract["state"],
            "source_version": source_contract["version"],
            "idempotency_sha256": idempotency_digest,
            "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        }
    }

    from servers.tasks import ingest_memory_event_task

    ingest_memory_event_task.delay(
        server_id=server.id,
        source_kind=source_contract["source_kind"],
        actor_kind=source_contract["actor_kind"],
        source_ref=source_contract["source_ref"],
        session_id=None,
        event_type=f"devops_{family}_{transition_token}"[:80],
        raw_text=excerpt,
        structured_payload=payload,
        importance_hint=_importance_for(family=family, outcome=source_contract["outcome"]),
        actor_user_id=source_contract["actor_user_id"],
        force_compact=False,
        event_metadata=event_metadata,
        idempotency_key_override=idempotency_key,
    )
    return idempotency_key


def _source_contract(*, server: Server, source: Any, event_family: str) -> dict[str, Any]:
    if not getattr(source, "pk", None):
        raise DevOpsMemoryEventError("A persisted source is required", code="source_invalid")
    object_type = ""
    source_kind = "system"
    actor_kind = "system"
    actor_user_id = None
    state = ""
    outcome = ""
    observed_at = None
    started_at = None
    resolved_at = None
    version_at = None
    exit_code = None

    if isinstance(source, ServerWatcherDraft):
        _require_family(event_family, {"incident"})
        _require_server(source.server_id, server.id)
        object_type = "servers.server_watcher_draft"
        source_kind = "watcher"
        actor_kind = "watcher"
        actor_user_id = source.acknowledged_by_id
        state = source.status
        outcome = "resolved" if state == ServerWatcherDraft.STATUS_RESOLVED else "unresolved"
        observed_at = source.last_seen_at or source.first_seen_at
        started_at = source.first_seen_at
        resolved_at = source.resolved_at
        version_at = source.resolved_at or source.acknowledged_at or source.last_seen_at
    elif isinstance(source, ServerAlert):
        _require_family(event_family, {"alert"})
        _require_server(source.server_id, server.id)
        object_type = "servers.server_alert"
        source_kind = "monitoring"
        actor_kind = "system" if source.is_resolved else "watcher"
        actor_user_id = source.resolved_by_id
        state = "resolved" if source.is_resolved else "open"
        outcome = state
        observed_at = source.resolved_at or source.created_at
        started_at = source.created_at
        resolved_at = source.resolved_at
        version_at = source.resolved_at or source.created_at
    elif isinstance(source, ServerHealthCheck):
        _require_family(event_family, {"monitoring"})
        _require_server(source.server_id, server.id)
        object_type = "servers.server_health_check"
        source_kind = "monitoring"
        state = source.status
        outcome = "healthy" if state == ServerHealthCheck.STATUS_HEALTHY else "degraded"
        observed_at = source.checked_at
        started_at = source.checked_at
        version_at = source.checked_at
    elif isinstance(source, ServerCommandHistory):
        _require_family(event_family, {"deploy"})
        _require_server(source.server_id, server.id)
        object_type = "servers.server_command_history"
        source_kind = {
            ServerCommandHistory.SOURCE_TERMINAL: "terminal",
            ServerCommandHistory.SOURCE_AGENT: "agent_event",
            ServerCommandHistory.SOURCE_PIPELINE: "pipeline",
            ServerCommandHistory.SOURCE_API: "system",
            ServerCommandHistory.SOURCE_SYSTEM: "system",
        }.get(source.source_kind, "system")
        actor_kind = {
            ServerCommandHistory.ACTOR_HUMAN: "human",
            ServerCommandHistory.ACTOR_AGENT: "agent",
            ServerCommandHistory.ACTOR_PIPELINE: "system",
            ServerCommandHistory.ACTOR_SYSTEM: "system",
        }.get(source.actor_kind, "system")
        actor_user_id = source.user_id
        state = "completed"
        exit_code = source.exit_code
        outcome = "succeeded" if exit_code == 0 else "failed" if isinstance(exit_code, int) else "unknown"
        observed_at = source.executed_at
        started_at = source.executed_at
        resolved_at = source.executed_at
        version_at = source.executed_at
    elif isinstance(source, PlaybookRun):
        _require_family(event_family, {"playbook"})
        _require_project(source.project_id, server.project_id)
        if server.id not in _integer_ids(source.target_server_ids):
            raise DevOpsMemoryEventError("Playbook run does not target this server", code="source_server_mismatch")
        object_type = "servers.playbook_run"
        source_kind = "pipeline"
        actor_user_id = source.user_id
        state = source.status
        outcome = _run_outcome(source.status)
        observed_at = source.finished_at or source.started_at or source.created_at
        started_at = source.started_at
        resolved_at = source.finished_at
        version_at = source.finished_at or source.started_at or source.created_at
    elif isinstance(source, AgentRun):
        _require_family(event_family, {"agent_run"})
        _require_project(source.project_id, server.project_id)
        _require_server(source.server_id, server.id)
        object_type = "servers.agent_run"
        source_kind = "agent_run"
        actor_kind = "agent"
        actor_user_id = source.user_id
        state = source.status
        outcome = _run_outcome(source.status)
        observed_at = source.completed_at or source.started_at
        started_at = source.started_at
        resolved_at = source.completed_at
        version_at = source.completed_at or source.started_at
    elif isinstance(source, PipelineRun):
        _require_family(event_family, {"pipeline"})
        _require_project(source.project_id, server.project_id)
        if server.id not in pipeline_snapshot_server_ids(source.nodes_snapshot):
            raise DevOpsMemoryEventError(
                "Pipeline run has no validated reference to this server", code="source_server_mismatch"
            )
        object_type = "studio.pipeline_run"
        source_kind = "pipeline"
        actor_user_id = source.triggered_by_id
        state = source.status
        outcome = _run_outcome(source.status)
        observed_at = source.finished_at or source.started_at or source.created_at
        started_at = source.started_at
        resolved_at = source.finished_at
        version_at = source.finished_at or source.started_at or source.created_at
    else:
        raise DevOpsMemoryEventError("Unsupported DevOps event source", code="source_type_invalid")

    return {
        "object_type": object_type,
        "id": int(source.pk),
        "state": _bounded_token(state, field="source_state"),
        "version": _iso(version_at),
        "outcome": _bounded_token(outcome, field="outcome"),
        "observed_at": _iso(observed_at),
        "started_at": _iso(started_at),
        "resolved_at": _iso(resolved_at),
        "source_ref": f"{object_type}:{source.pk}",
        "source_kind": source_kind,
        "actor_kind": actor_kind,
        "actor_user_id": actor_user_id,
        "exit_code": exit_code,
    }


def _load_persisted_source(source: Any) -> Any:
    for model in (
        ServerWatcherDraft,
        ServerAlert,
        ServerHealthCheck,
        ServerCommandHistory,
        PlaybookRun,
        AgentRun,
        PipelineRun,
    ):
        if isinstance(source, model):
            persisted = model.objects.filter(pk=getattr(source, "pk", None)).first()
            if persisted is None:
                break
            return persisted
    raise DevOpsMemoryEventError("A persisted supported source is required", code="source_invalid")


def _authorized_evidence_refs(*, server: Server, source: Any, source_contract: dict[str, Any]) -> list[str]:
    refs = [source_contract["source_ref"], f"server:{server.id}", f"project:{server.project_id}"]
    if isinstance(source, PlaybookRun):
        if source.playbook_id:
            refs.append(f"playbook:{source.playbook_id}")
        if source.revision_id:
            refs.append(f"playbook_revision:{source.revision_id}")
        if source.validation_id:
            refs.append(f"playbook_validation:{source.validation_id}")
    elif isinstance(source, AgentRun) and source.agent_id:
        refs.append(f"server_agent:{source.agent_id}")
    elif isinstance(source, PipelineRun):
        refs.append(f"studio_pipeline:{source.pipeline_id}")
    return refs


def _idempotency_digest(
    *, server_id: int, object_type: str, object_id: int, transition: str, outcome: str, version: str
) -> str:
    canonical = _canonical_json(
        {
            "schema_version": SCHEMA_VERSION,
            "server_id": server_id,
            "object_type": object_type,
            "object_id": object_id,
            "transition": transition,
            "outcome": outcome,
            "version": version,
        }
    )
    return hashlib.sha256(canonical).hexdigest()


def _summary_envelope(value: str, *, field: str) -> dict[str, str]:
    summary = _redacted_bounded_text(value, limit=MAX_SUMMARY_BYTES, field=field)
    if not summary:
        return {}
    return {
        "redacted_summary": summary,
        "sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
    }


def _redacted_bounded_text(value: str, *, limit: int, field: str) -> str:
    text = str(value or "")
    if len(text.encode("utf-8")) > limit:
        raise DevOpsMemoryEventError(f"{field} exceeds its byte limit", code=f"{field}_too_large")
    redacted, _payload, _report, _hashes = redact_for_storage(raw_text=text, payload={})
    if len(redacted.encode("utf-8")) > limit:
        raise DevOpsMemoryEventError(f"{field} exceeds its byte limit after redaction", code=f"{field}_too_large")
    return redacted


def _bounded_token(value: Any, *, field: str) -> str:
    token = str(value or "").strip().lower()
    if not _TOKEN_RE.fullmatch(token):
        raise DevOpsMemoryEventError(f"Invalid {field}", code=f"{field}_invalid")
    return token


def _bounded_ref(value: Any, *, field: str, allow_blank: bool = False) -> str:
    reference = str(value or "").strip()
    if not reference and allow_blank:
        return ""
    if not _REF_RE.fullmatch(reference):
        raise DevOpsMemoryEventError(f"Invalid {field}", code=f"{field}_invalid")
    return reference


def _require_family(actual: str, allowed: set[str]) -> None:
    if actual not in allowed:
        raise DevOpsMemoryEventError("Event family does not match its source", code="source_family_mismatch")


def _require_server(actual: int | None, expected: int) -> None:
    if actual != expected:
        raise DevOpsMemoryEventError("Source does not belong to this server", code="source_server_mismatch")


def _require_project(actual: int | None, expected: int) -> None:
    if actual != expected:
        raise DevOpsMemoryEventError("Source does not belong to this project", code="source_project_mismatch")


def _run_outcome(status: str) -> str:
    return {
        "completed": "succeeded",
        "failed": "failed",
        "partial": "partial",
        "cancelled": "cancelled",
        "stopped": "stopped",
    }.get(str(status or ""), "in_progress")


def _integer_ids(values: Any) -> set[int]:
    if not isinstance(values, list):
        return set()
    result: set[int] = set()
    for value in values[:100]:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def pipeline_snapshot_server_ids(nodes_snapshot: Any) -> set[int]:
    """Extract only explicitly configured WebTerm server IDs from a run snapshot."""
    if not isinstance(nodes_snapshot, list):
        return set()
    result: set[int] = set()
    for node in nodes_snapshot[:200]:
        if not isinstance(node, dict):
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        candidates = [data]
        if isinstance(data.get("config"), dict):
            candidates.append(data["config"])
        for candidate in candidates:
            result.update(_integer_ids(candidate.get("server_ids")))
            value = candidate.get("server_id")
            try:
                if value not in (None, ""):
                    result.add(int(value))
            except (TypeError, ValueError):
                continue
    return result


def _importance_for(*, family: str, outcome: str) -> float:
    if outcome in {"failed", "degraded", "unresolved"}:
        return 0.9
    if family in {"incident", "alert", "deploy"}:
        return 0.78
    return 0.68


def _iso(value: datetime | None) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
