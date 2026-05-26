from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from app.agent_kernel.memory.compaction import compact_text, unique_preserving_order
from app.agent_kernel.memory.pattern_utils import (
    automation_candidate_lines,
    classify_command_intent,
    classify_sequence_intent,
    describe_pattern_intent,
    is_automation_candidate,
    is_skill_draft_candidate,
    is_verification_command,
    normalize_command_pattern,
    pattern_candidate_lines,
    pattern_enhancement_metadata,
    pattern_key_suffix,
    pattern_metadata,
    skill_draft_lines,
)
from app.agent_kernel.memory.snapshot_utils import event_output_markers, render_snapshot_lines
from app.agent_kernel.memory.types import (
    AUTOMATION_CANDIDATE_PREFIX,
    PATTERN_CANDIDATE_PREFIX,
    SKILL_DRAFT_PREFIX,
    OperationalPattern,
)
from servers.adapters.django_memory_snapshots import archive_missing_candidate_snapshots, upsert_snapshot


def derive_operational_patterns(server_id: int) -> list[OperationalPattern]:
    from servers.models import ServerMemoryEvent

    now = timezone.now()
    recent = list(
        ServerMemoryEvent.objects.filter(
            server_id=server_id,
            event_type="command_executed",
            created_at__gte=now - timedelta(days=30),
        ).order_by("created_at", "id")[:220]
    )
    buckets: dict[str, dict[str, Any]] = {}
    session_events: dict[str, list[Any]] = {}
    for event in recent:
        payload = event.structured_payload or {}
        command = str(payload.get("command") or "").strip()
        if command:
            normalized = normalize_command_pattern(command)
            bucket = buckets.setdefault(
                normalized,
                {
                    "display_command": compact_text(command, limit=140),
                    "occurrences": 0,
                    "successful_runs": 0,
                    "measured_runs": 0,
                    "actor_kinds": set(),
                    "source_kinds": set(),
                    "verification_hits": 0,
                    "sample_outputs": [],
                    "common_cwds": [],
                    "session_keys": set(),
                    "last_seen": event.created_at,
                    "intent": classify_command_intent(command),
                },
            )
            age_days = (now - event.created_at).days if event.created_at else 15
            temporal_weight = max(0.1, 1.0 - age_days / 30.0)
            bucket["occurrences"] += 1
            bucket["weighted_occurrences"] = bucket.get("weighted_occurrences", 0.0) + temporal_weight
            bucket["actor_kinds"].add(str(event.actor_kind or "system"))
            bucket["source_kinds"].add(str(event.source_kind or "system"))
            if is_verification_command(command):
                bucket["verification_hits"] += 1
            output_markers = event_output_markers(event)
            if output_markers:
                bucket["sample_outputs"].extend(output_markers[:2])
            cwd = compact_text(str(payload.get("cwd") or "").strip(), limit=120)
            if cwd:
                bucket["common_cwds"].append(cwd)
            if event.created_at and (bucket["last_seen"] is None or event.created_at > bucket["last_seen"]):
                bucket["last_seen"] = event.created_at
            exit_code = payload.get("exit_code")
            if isinstance(exit_code, int):
                bucket["measured_runs"] += 1
                if exit_code == 0:
                    bucket["successful_runs"] += 1
            session_key = str(event.session_id or event.source_ref or "").strip()
            if session_key:
                bucket["session_keys"].add(session_key)
                session_events.setdefault(session_key, []).append(event)

    patterns: list[OperationalPattern] = []
    for normalized, bucket in buckets.items():
        occurrences = int(bucket["occurrences"])
        weighted_occurrences = float(bucket.get("weighted_occurrences", occurrences))
        measured_runs = int(bucket["measured_runs"])
        successful_runs = int(bucket["successful_runs"])
        success_rate = (successful_runs / measured_runs) if measured_runs else 1.0
        if weighted_occurrences < 1.2 and occurrences < 2 and successful_runs < 2:
            continue
        patterns.append(
            OperationalPattern(
                pattern_kind="command",
                display_command=str(bucket["display_command"]),
                normalized_command=normalized,
                intent=str(bucket["intent"]),
                intent_label=describe_pattern_intent(
                    [str(bucket["display_command"])],
                    intent=str(bucket["intent"]),
                    sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=3)),
                ),
                commands=(str(bucket["display_command"]),),
                occurrences=occurrences,
                successful_runs=successful_runs,
                measured_runs=measured_runs,
                success_rate=success_rate,
                actor_kinds=tuple(sorted(bucket["actor_kinds"])),
                source_kinds=tuple(sorted(bucket["source_kinds"])),
                verification_rate=float(bucket["verification_hits"] or 0) / max(occurrences, 1),
                has_verification_step=bool(bucket["verification_hits"]),
                sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=3)),
                common_cwds=tuple(unique_preserving_order(bucket["common_cwds"], limit=3)),
                distinct_sessions=max(1, len(bucket["session_keys"])) if bucket["session_keys"] else 0,
                last_seen=bucket["last_seen"],
            )
        )
    patterns.extend(derive_sequence_patterns(session_events))
    patterns.sort(
        key=lambda item: (
            1 if item.pattern_kind == "sequence" else 0,
            item.occurrences,
            item.success_rate,
            item.verification_rate,
            1 if "human" in item.actor_kinds else 0,
            item.last_seen or timezone.now(),
        ),
        reverse=True,
    )
    return patterns[:12]


def derive_sequence_patterns(session_events: dict[str, list[Any]]) -> list[OperationalPattern]:
    buckets: dict[str, dict[str, Any]] = {}
    for session_key, events in session_events.items():
        ordered = [item for item in sorted(events, key=lambda event: (event.created_at, event.id)) if item is not None]
        if len(ordered) < 2:
            continue
        max_window = min(3, len(ordered))
        for size in range(2, max_window + 1):
            for index in range(0, len(ordered) - size + 1):
                window = ordered[index : index + size]
                commands: list[str] = []
                normalized_commands: list[str] = []
                output_markers: list[str] = []
                common_cwds: list[str] = []
                actor_kinds: set[str] = set()
                source_kinds: set[str] = set()
                exit_codes: list[int] = []
                verification_hits = 0
                for event in window:
                    payload = event.structured_payload or {}
                    command = str(payload.get("command") or "").strip()
                    if not command:
                        commands = []
                        break
                    commands.append(compact_text(command, limit=120))
                    normalized_commands.append(normalize_command_pattern(command))
                    actor_kinds.add(str(event.actor_kind or "system"))
                    source_kinds.add(str(event.source_kind or "system"))
                    if is_verification_command(command):
                        verification_hits += 1
                    output_markers.extend(event_output_markers(event)[:1])
                    cwd = compact_text(str(payload.get("cwd") or "").strip(), limit=120)
                    if cwd:
                        common_cwds.append(cwd)
                    exit_code = payload.get("exit_code")
                    if isinstance(exit_code, int):
                        exit_codes.append(exit_code)
                if len(commands) != size or len(set(normalized_commands)) < 2:
                    continue
                signature = " => ".join(normalized_commands)
                bucket = buckets.setdefault(
                    signature,
                    {
                        "commands": tuple(commands),
                        "intent": classify_sequence_intent(commands),
                        "occurrences": 0,
                        "successful_runs": 0,
                        "measured_runs": 0,
                        "verification_hits": 0,
                        "actor_kinds": set(),
                        "source_kinds": set(),
                        "sample_outputs": [],
                        "common_cwds": [],
                        "session_keys": set(),
                        "last_seen": window[-1].created_at,
                    },
                )
                bucket["occurrences"] += 1
                bucket["actor_kinds"].update(actor_kinds)
                bucket["source_kinds"].update(source_kinds)
                bucket["session_keys"].add(session_key)
                bucket["verification_hits"] += 1 if verification_hits else 0
                if len(exit_codes) == size:
                    bucket["measured_runs"] += 1
                    if all(code == 0 for code in exit_codes):
                        bucket["successful_runs"] += 1
                bucket["sample_outputs"].extend(output_markers[:2])
                bucket["common_cwds"].extend(common_cwds[:2])
                if window[-1].created_at and (
                    bucket["last_seen"] is None or window[-1].created_at > bucket["last_seen"]
                ):
                    bucket["last_seen"] = window[-1].created_at

    patterns: list[OperationalPattern] = []
    for signature, bucket in buckets.items():
        occurrences = int(bucket["occurrences"])
        if occurrences < 2:
            continue
        measured_runs = int(bucket["measured_runs"])
        successful_runs = int(bucket["successful_runs"])
        success_rate = (successful_runs / measured_runs) if measured_runs else 1.0
        verification_rate = float(bucket["verification_hits"] or 0) / max(occurrences, 1)
        patterns.append(
            OperationalPattern(
                pattern_kind="sequence",
                display_command=" -> ".join(bucket["commands"]),
                normalized_command=signature,
                intent=str(bucket["intent"]),
                intent_label=describe_pattern_intent(
                    list(bucket["commands"]),
                    intent=str(bucket["intent"]),
                    sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=4)),
                ),
                commands=tuple(bucket["commands"]),
                occurrences=occurrences,
                successful_runs=successful_runs,
                measured_runs=measured_runs,
                success_rate=success_rate,
                actor_kinds=tuple(sorted(bucket["actor_kinds"])),
                source_kinds=tuple(sorted(bucket["source_kinds"])),
                verification_rate=verification_rate,
                has_verification_step=verification_rate >= 0.5
                or any(is_verification_command(command) for command in bucket["commands"]),
                sample_outputs=tuple(unique_preserving_order(bucket["sample_outputs"], limit=4)),
                common_cwds=tuple(unique_preserving_order(bucket["common_cwds"], limit=3)),
                distinct_sessions=max(1, len(bucket["session_keys"])) if bucket["session_keys"] else 0,
                last_seen=bucket["last_seen"],
            )
        )
    return patterns


def promote_pattern_candidates(
    *,
    server_id: int,
    patterns: list[OperationalPattern],
    snapshots: list[Any],
    enhancements: dict[str, dict[str, Any]] | None = None,
) -> dict[str, int]:
    active_keys: set[str] = set()
    pattern_candidates = 0
    automation_candidates = 0
    skill_drafts = 0
    enhancements = enhancements or {}

    for pattern in patterns:
        if pattern.occurrences < 2:
            continue
        enhancement = enhancements.get(pattern.normalized_command) or {}
        pattern_key = f"{PATTERN_CANDIDATE_PREFIX}{pattern_key_suffix(pattern)}"
        active_keys.add(pattern_key)
        upsert_snapshot(
            server_id=server_id,
            memory_key=pattern_key,
            title=f"Learned Pattern: {pattern.intent} :: {pattern.display_command[:72]}",
            content=render_snapshot_lines(pattern_candidate_lines(pattern, enhancement=enhancement), fallback=pattern.display_command),
            source_kind="dream",
            importance_score=0.68 if pattern.pattern_kind == "sequence" else 0.64,
            stability_score=min(0.9, 0.45 + min(pattern.occurrences, 6) * 0.06 + (0.05 if pattern.pattern_kind == "sequence" else 0.0)),
            confidence=min(0.97, max(0.58, pattern.success_rate + (0.04 if pattern.has_verification_step else 0.0))),
            metadata=pattern_metadata(pattern) | pattern_enhancement_metadata(enhancement),
        )
        pattern_candidates += 1

        if is_automation_candidate(pattern):
            automation_key = f"{AUTOMATION_CANDIDATE_PREFIX}{pattern_key_suffix(pattern)}"
            active_keys.add(automation_key)
            upsert_snapshot(
                server_id=server_id,
                memory_key=automation_key,
                title=f"Automation Candidate: {pattern.intent} :: {pattern.display_command[:68]}",
                content=render_snapshot_lines(
                    automation_candidate_lines(pattern, enhancement=enhancement),
                    fallback=pattern.display_command,
                ),
                source_kind="dream",
                importance_score=0.78 if pattern.pattern_kind == "sequence" else 0.72,
                stability_score=min(0.92, 0.5 + min(pattern.occurrences, 6) * 0.05 + (0.06 if pattern.pattern_kind == "sequence" else 0.0)),
                confidence=min(0.98, max(0.64, pattern.success_rate + (0.04 if pattern.has_verification_step else 0.0))),
                metadata=pattern_metadata(pattern) | {"candidate_kind": "automation"} | pattern_enhancement_metadata(enhancement),
            )
            automation_candidates += 1
            if is_skill_draft_candidate(pattern):
                skill_key = f"{SKILL_DRAFT_PREFIX}{pattern_key_suffix(pattern)}"
                active_keys.add(skill_key)
                upsert_snapshot(
                    server_id=server_id,
                    memory_key=skill_key,
                    title=f"Skill Draft: {pattern.intent} :: {pattern.display_command[:68]}",
                    content=render_snapshot_lines(skill_draft_lines(pattern, enhancement=enhancement), fallback=pattern.display_command),
                    source_kind="dream",
                    importance_score=0.84 if pattern.pattern_kind == "sequence" else 0.76,
                    stability_score=min(0.94, 0.56 + min(pattern.occurrences, 7) * 0.04 + (0.08 if pattern.pattern_kind == "sequence" else 0.0)),
                    confidence=min(0.99, max(0.68, pattern.success_rate + (0.05 if pattern.has_verification_step else 0.0))),
                    metadata=pattern_metadata(pattern) | {"candidate_kind": "skill_draft"} | pattern_enhancement_metadata(enhancement),
                )
                skill_drafts += 1

    archive_missing_candidate_snapshots(server_id, active_keys=active_keys)
    return {
        "pattern_candidates": pattern_candidates,
        "automation_candidates": automation_candidates,
        "skill_drafts": skill_drafts,
    }
