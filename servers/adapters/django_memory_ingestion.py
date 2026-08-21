from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from app.agent_kernel.memory.compaction import compact_text, extract_signal_lines, unique_preserving_order
from app.agent_kernel.memory.line_filters import filter_memory_lines
from app.agent_kernel.memory.redaction import payload_preview, redact_for_storage
from app.agent_kernel.memory.trust import (
    aggregate_trust_metadata,
    build_idempotency_key,
    enrich_metadata_with_trust,
    stable_payload_hash,
)

_DEVOPS_METADATA_KEYS = {
    "schema_version",
    "event_family",
    "source_object_type",
    "source_object_id",
    "source_state",
    "source_version",
    "idempotency_sha256",
    "contract_sha256",
}
_DEVOPS_EVENT_FAMILIES = {"incident", "alert", "monitoring", "deploy", "pipeline", "playbook", "agent_run"}
_DEVOPS_SOURCE_TYPES = {
    "servers.server_watcher_draft",
    "servers.server_alert",
    "servers.server_health_check",
    "servers.server_command_history",
    "servers.playbook_run",
    "servers.agent_run",
    "studio.pipeline_run",
}


def ingest_event(
    store,
    server_id: int,
    *,
    source_kind: str,
    actor_kind: str,
    event_type: str,
    raw_text: str = "",
    structured_payload: dict[str, Any] | None = None,
    source_ref: str = "",
    session_id: str | None = "",
    importance_hint: float = 0.5,
    actor_user_id: int | None = None,
    force_compact: bool = False,
    event_metadata: dict[str, Any] | None = None,
    idempotency_key_override: str = "",
) -> str:
    from servers.models import Server, ServerMemoryEvent

    structured_payload = structured_payload or {}
    # Monitoring events intentionally have no terminal/session identity and
    # pass ``None``.  Normalize that supported input before length-bounding it
    # for the model field.
    session_id = str(session_id or "")
    server = Server.objects.filter(pk=server_id).select_related("user").first()
    if server is None:
        return ""

    policy = store._get_or_create_policy_sync(user_id=server.user_id)
    if not bool(getattr(policy, "is_enabled", True)):
        return ""
    if event_metadata is not None and (
        not isinstance(event_metadata, dict)
        or set(event_metadata) != {"devops_event"}
        or not isinstance(event_metadata.get("devops_event"), dict)
    ):
        raise ValueError("event_metadata must contain only a devops_event object")
    if event_metadata:
        _validate_devops_event_metadata(event_metadata["devops_event"])
    redacted_text, redacted_payload, redaction_report, redaction_hashes = redact_for_storage(
        raw_text=raw_text,
        payload=structured_payload,
    )
    redacted_metadata: dict[str, Any] = {}
    if event_metadata:
        _unused_text, redacted_metadata_value, metadata_report, metadata_hashes = redact_for_storage(
            payload=event_metadata,
        )
        if not isinstance(redacted_metadata_value, dict):
            raise ValueError("event_metadata must redact to an object")
        redacted_metadata = redacted_metadata_value
        for key, value in metadata_report.items():
            redaction_report[key] = redaction_report.get(key, 0) + int(value)
        redaction_hashes = list(dict.fromkeys([*redaction_hashes, *metadata_hashes]))
    redacted_text = compact_text(redacted_text, limit=8000 if policy.allow_sensitive_raw else 4000)
    storage_metadata = enrich_metadata_with_trust(
        redacted_metadata,
        source_kind=source_kind,
        actor_kind=actor_kind,
        event_type=event_type,
        payload=redacted_payload,
        source_ref=source_ref,
    )
    payload_hash = stable_payload_hash(raw_text=redacted_text, payload=redacted_payload)
    normalized_override = str(idempotency_key_override or "").strip().lower()
    if normalized_override and (
        not normalized_override.startswith("devops:v1:")
        or len(normalized_override) != 74
        or any(character not in "0123456789abcdef" for character in normalized_override[10:])
    ):
        raise ValueError("Invalid DevOps event idempotency key")
    if normalized_override and not event_metadata:
        raise ValueError("DevOps idempotency override requires validated devops_event metadata")
    if event_metadata and (
        not normalized_override
        or event_metadata["devops_event"]["idempotency_sha256"] != normalized_override[10:]
    ):
        raise ValueError("DevOps metadata idempotency digest does not match the override")
    idempotency_key = normalized_override or build_idempotency_key(
        server_id=server_id,
        source_kind=source_kind,
        source_ref=source_ref,
        session_id=session_id,
        event_type=event_type,
        payload_hash=payload_hash,
    )

    event, created = ServerMemoryEvent.objects.get_or_create(
        server_id=server_id,
        idempotency_key=idempotency_key,
        defaults={
            "actor_user_id": actor_user_id,
            "source_kind": source_kind,
            "actor_kind": actor_kind,
            "source_ref": source_ref[:255],
            "session_id": session_id[:120],
            "event_type": event_type[:80],
            "raw_text_redacted": redacted_text,
            "structured_payload": redacted_payload,
            "metadata": storage_metadata,
            "payload_hash": payload_hash,
            "importance_hint": max(0.0, min(float(importance_hint or 0.5), 1.0)),
            "redaction_report": redaction_report,
            "redaction_hashes": redaction_hashes,
        },
    )
    if created:
        maybe_compact_event_group(
            event, threshold=max(int(policy.nearline_event_threshold or 6), 2), force=force_compact
        )
    return str(event.pk)


def _validate_devops_event_metadata(metadata: dict[str, Any]) -> None:
    if set(metadata) != _DEVOPS_METADATA_KEYS:
        raise ValueError("devops_event metadata has unknown or missing keys")
    if metadata.get("schema_version") != "devops_event.v1":
        raise ValueError("devops_event metadata has an invalid schema version")
    if metadata.get("event_family") not in _DEVOPS_EVENT_FAMILIES:
        raise ValueError("devops_event metadata has an invalid event family")
    if metadata.get("source_object_type") not in _DEVOPS_SOURCE_TYPES:
        raise ValueError("devops_event metadata has an invalid source object type")
    source_id = metadata.get("source_object_id")
    if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id <= 0:
        raise ValueError("devops_event metadata has an invalid source object id")
    for key in ("source_state", "source_version"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value or len(value) > 80:
            raise ValueError(f"devops_event metadata has an invalid {key}")
    for key in ("idempotency_sha256", "contract_sha256"):
        value = metadata.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"devops_event metadata has an invalid {key}")


def maybe_compact_event_group(event, *, threshold: int, force: bool) -> None:
    from servers.models import ServerMemoryEvent

    filters = event_group_filters(event)
    count = ServerMemoryEvent.objects.filter(**filters, is_archived=False, compacted_episode__isnull=True).count()
    if (
        force
        or count >= threshold
        or event.event_type
        in {
            "session_closed",
            "run_completed",
            "run_failed",
            "run_stopped",
        }
    ):
        compact_group(
            server_id=event.server_id,
            source_kind=event.source_kind,
            source_ref=(event.source_ref or ""),
            session_id=(event.session_id or ""),
            force=force,
        )


def event_group_filters(event) -> dict[str, Any]:
    filters = {"server_id": event.server_id, "source_kind": event.source_kind}
    if event.session_id:
        filters["session_id"] = event.session_id
    elif event.source_ref:
        filters["source_ref"] = event.source_ref
    else:
        filters["created_at__gte"] = timezone.now() - timedelta(hours=6)
    return filters


def compact_open_groups(server_id: int, *, force: bool = False) -> int:
    from servers.models import ServerMemoryEvent

    groups: set[tuple[str, str, str]] = set()
    for event in ServerMemoryEvent.objects.filter(
        server_id=server_id,
        is_archived=False,
        compacted_episode__isnull=True,
    ).order_by("-created_at")[:80]:
        groups.add((event.source_kind, event.source_ref or "", event.session_id or ""))
    compacted = 0
    for source_kind, source_ref, session_id in groups:
        compacted += compact_group(
            server_id=server_id,
            source_kind=source_kind,
            source_ref=source_ref,
            session_id=session_id,
            force=force,
        )
    return compacted


def compact_group(
    *,
    server_id: int,
    source_kind: str,
    source_ref: str = "",
    session_id: str = "",
    force: bool = False,
) -> int:
    from servers.models import ServerMemoryEpisode, ServerMemoryEvent

    filters = {
        "server_id": server_id,
        "source_kind": source_kind,
        "is_archived": False,
        "compacted_episode__isnull": True,
    }
    if session_id:
        filters["session_id"] = session_id
    elif source_ref:
        filters["source_ref"] = source_ref
    else:
        filters["created_at__gte"] = timezone.now() - timedelta(hours=6)

    with transaction.atomic():
        events = list(
            ServerMemoryEvent.objects.select_for_update().filter(**filters).order_by("created_at", "id")[:120]
        )
        if not events:
            return 0
        if len(events) < 2 and not force:
            return 0

        episode_kind = episode_kind_for_source(source_kind, events)
        summary_lines = episode_summary_lines(events)
        commands = extract_commands(events)[:12]
        if episode_kind == "terminal_session" and not summary_lines and not commands:
            return 0
        title = episode_title(source_kind, episode_kind, events)
        summary = build_episode_summary(events, summary_lines=summary_lines)
        metadata = aggregate_trust_metadata(events) | {
            "source_kind": source_kind,
            "event_types": list(dict.fromkeys(event.event_type for event in events))[:12],
            "commands": commands,
        }
        episode = ServerMemoryEpisode.objects.create(
            server_id=server_id,
            episode_kind=episode_kind,
            source_kind=source_kind,
            source_ref=source_ref,
            session_id=session_id,
            title=title,
            summary=summary,
            event_count=len(events),
            importance_score=max(float(event.importance_hint or 0.5) for event in events),
            confidence=min(0.95, 0.55 + min(len(events), 12) * 0.03),
            metadata=metadata,
            first_event_at=events[0].created_at,
            last_event_at=events[-1].created_at,
        )
        ServerMemoryEvent.objects.filter(pk__in=[event.pk for event in events]).update(
            compacted_episode=episode,
            compacted_at=timezone.now(),
        )
    return 1


def episode_kind_for_source(source_kind: str, events: list[Any]) -> str:
    if source_kind == "terminal":
        return "terminal_session"
    if source_kind in {"agent_run", "agent_event"}:
        text_blob = "\n".join((event.raw_text_redacted or "") for event in events).lower()
        if any(term in text_blob for term in ("deploy", "rollout", "rollback", "release")):
            return "deploy_operation"
        if any(event.event_type == "incident" for event in events):
            return "incident"
        return "agent_investigation"
    if source_kind in {"monitoring", "watcher"}:
        return "incident"
    if source_kind == "pipeline":
        return "pipeline_operation"
    return "misc"


def episode_title(source_kind: str, episode_kind: str, events: list[Any]) -> str:
    first = events[0]
    if episode_kind == "terminal_session":
        return f"Human terminal session ({first.created_at:%Y-%m-%d %H:%M})"
    if episode_kind == "deploy_operation":
        return f"Deploy operation ({first.created_at:%Y-%m-%d %H:%M})"
    if episode_kind == "incident":
        return f"Incident window ({first.created_at:%Y-%m-%d %H:%M})"
    if episode_kind == "agent_investigation":
        return f"Agent investigation ({first.created_at:%Y-%m-%d %H:%M})"
    if source_kind == "pipeline":
        return f"Pipeline server activity ({first.created_at:%Y-%m-%d %H:%M})"
    return f"{source_kind} activity ({first.created_at:%Y-%m-%d %H:%M})"


def is_transport_event_type(event_type: str) -> bool:
    return event_type in {"session_opened", "session_closed"}


def episode_summary_lines(events: list[Any]) -> list[str]:
    lines: list[str] = []
    for event in events:
        event_type = str(getattr(event, "event_type", "") or "")
        if is_transport_event_type(event_type):
            continue
        if event.raw_text_redacted:
            lines.extend(extract_signal_lines(event.raw_text_redacted, max_items=2))
        preview = payload_preview(event.structured_payload, limit=180)
        if preview:
            lines.append(f"{event_type}: {preview}")
    return filter_memory_lines(lines, limit=10)


def build_episode_summary(events: list[Any], *, summary_lines: list[str] | None = None) -> str:
    normalized = summary_lines if summary_lines is not None else episode_summary_lines(events)
    if not normalized:
        normalized = ["Содержательная выжимка пока недоступна."]
    return "\n".join(f"- {line}" for line in normalized[:10])


def extract_commands(events: list[Any]) -> list[str]:
    commands: list[str] = []
    for event in events:
        command = str((event.structured_payload or {}).get("command") or "").strip()
        if command:
            commands.append(compact_text(command, limit=140))
    return unique_preserving_order(commands, limit=16)
