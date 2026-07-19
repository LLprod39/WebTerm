from __future__ import annotations

from app.agent_kernel.domain.specs import MemoryRecord, ServerMemoryCard
from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.repair import compute_freshness_score
from app.agent_kernel.memory.trust import (
    TRUST_AGENT_REPORTED,
    TRUST_HUMAN_OBSERVED,
    TRUST_MANUAL_VERIFIED,
    TRUST_SYSTEM_MEASURED,
    VERIFICATION_MEASURED,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_VERIFIED,
    prompt_provenance_label,
)

CANONICAL_PRIORITIES = {
    "profile": 3.0,
    "access": 2.9,
    "risks": 2.8,
    "runbook": 2.7,
    "recent_changes": 2.6,
    "human_habits": 2.5,
}


def _snapshot_lines(content: str, *, limit: int = 180) -> list[str]:
    return [compact_text(line.lstrip("- ").strip(), limit=limit) for line in content.splitlines() if line.strip()]


def _is_session_noise_line(line: str) -> bool:
    normalized = compact_text(str(line or ""), limit=220).lower()
    if not normalized:
        return True
    if normalized.startswith(("session_opened:", "session_closed:")):
        return True
    if normalized in {
        "ssh terminal session opened",
        "ssh terminal session closed",
    }:
        return True
    return bool(any(marker in normalized for marker in ("connection_id", "user_id")) and any(term in normalized for term in ("session_opened", "session_closed", "session opened", "session closed")))


def _clean_episode_summary(summary: str, *, limit: int = 3) -> str:
    lines = [line for line in _snapshot_lines(summary, limit=180) if not _is_session_noise_line(line)]
    if not lines:
        return ""
    return "; ".join(lines[:limit])


def _summarize_operational_playbook(title: str, content: str, *, metadata: dict | None = None) -> str | None:
    metadata = metadata or {}
    normalized_title = compact_text(str(title or ""), limit=90)
    category = str(metadata.get("category") or "").strip().lower()
    lowered_content = str(content or "").lower()
    is_operational = (
        normalized_title.lower().startswith("operational skill:")
        or "связанный skill:" in lowered_content
        or "workflow:" in lowered_content
        or category in {"solutions", "services"}
    )
    if not is_operational:
        return None

    focus_lines: list[str] = []
    for line in _snapshot_lines(content, limit=150):
        lowered = line.lower()
        if "открыть/редактировать skill" in lowered:
            continue
        if lowered.startswith(("связанный skill:", "когда использовать:", "workflow:", "команда:", "сигналы успеха:", "типовой cwd:")):
            focus_lines.append(line)
    if not focus_lines:
        focus_lines = _snapshot_lines(content, limit=150)[:2]
    if not focus_lines:
        return None
    return compact_text(f"{normalized_title}: {'; '.join(focus_lines[:2])}", limit=300)


def _record_priority(item) -> float:
    confidence = float(getattr(item, "confidence", 0.8) or 0.8)
    freshness = compute_freshness_score(getattr(item, "updated_at", None), getattr(item, "last_verified_at", None))
    base = confidence * freshness
    memory_key = str(getattr(item, "memory_key", "") or "")
    base += CANONICAL_PRIORITIES.get(memory_key, 0.0)
    if getattr(item, "last_verified_at", None):
        base += 0.4
    return base


def _provenance_metadata(trust_level: str, verification_status: str, *, source_actor_kind: str = "system") -> dict:
    return {
        "trust_level": trust_level,
        "verification_status": verification_status,
        "source_actor_kind": source_actor_kind,
    }


def _with_provenance(
    text: str,
    *,
    metadata: dict | None = None,
    confidence: float | None = None,
    last_verified_at=None,
    source_kind: str = "",
    source_ref: str = "",
) -> str:
    return (
        f"{prompt_provenance_label(metadata=metadata, confidence=confidence, last_verified_at=last_verified_at, source_kind=source_kind, source_ref=source_ref)} "
        f"{text}"
    )


def build_server_memory_card(
    server,
    *,
    global_rules=None,
    group_knowledge=None,
    snapshots=None,
    episodes=None,
    revalidations=None,
    latest_health=None,
    active_alerts=None,
    recent_runs=None,
    legacy_knowledge=None,
) -> ServerMemoryCard:
    tags = [item.strip() for item in (server.tags or "").split(",") if item.strip()]
    if server.group_id:
        tags.append(f"group:{server.group.name}")
    if server.network_config.get("vpn", {}).get("required"):
        tags.append("vpn")
    if server.has_proxy:
        tags.append("proxy")

    stable_facts: list[str] = []
    known_risks: list[str] = []
    incidents: list[str] = []
    recent_changes: list[str] = []
    playbooks: list[str] = []
    records: list[MemoryRecord] = []

    if global_rules:
        if global_rules.forbidden_commands:
            known_risks.append(
                _with_provenance(
                    "Запрещенные команды: " + ", ".join(global_rules.forbidden_commands[:6]),
                    metadata=_provenance_metadata(TRUST_MANUAL_VERIFIED, VERIFICATION_VERIFIED, source_actor_kind="human"),
                    confidence=0.9,
                    source_kind="global_rules",
                    source_ref=f"rules:{global_rules.id}",
                )
            )
        if global_rules.required_checks:
            known_risks.append(
                _with_provenance(
                    "Обязательные проверки: " + ", ".join(global_rules.required_checks[:6]),
                    metadata=_provenance_metadata(TRUST_MANUAL_VERIFIED, VERIFICATION_VERIFIED, source_actor_kind="human"),
                    confidence=0.9,
                    source_kind="global_rules",
                    source_ref=f"rules:{global_rules.id}",
                )
            )

    if getattr(server, "notes", ""):
        stable_facts.append(
            _with_provenance(
                compact_text(str(server.notes), limit=180),
                metadata=_provenance_metadata(TRUST_SYSTEM_MEASURED, VERIFICATION_MEASURED),
                confidence=0.8,
                source_kind="server_inventory",
                source_ref=f"server:{server.id}",
            )
        )
    if getattr(server, "corporate_context", ""):
        stable_facts.append(
            _with_provenance(
                compact_text(str(server.corporate_context), limit=180),
                metadata=_provenance_metadata(TRUST_SYSTEM_MEASURED, VERIFICATION_MEASURED),
                confidence=0.8,
                source_kind="server_inventory",
                source_ref=f"server:{server.id}",
            )
        )
    network_summary = server.get_network_context_summary()
    if network_summary and network_summary != "Стандартная сеть":
        stable_facts.append(
            _with_provenance(
                compact_text(network_summary, limit=160),
                metadata=_provenance_metadata(TRUST_SYSTEM_MEASURED, VERIFICATION_MEASURED),
                confidence=0.8,
                source_kind="server_inventory",
                source_ref=f"server:{server.id}",
            )
        )

    for item in list(group_knowledge or [])[:4]:
        records.append(
            MemoryRecord(
                domain="group",
                title=str(item.title),
                content=compact_text(str(item.content), limit=220),
                confidence=0.8,
                freshness_score=compute_freshness_score(item.updated_at),
                metadata={
                    "category": item.category,
                    "trust_level": TRUST_MANUAL_VERIFIED,
                    "verification_status": VERIFICATION_VERIFIED,
                    "source_actor_kind": "human",
                },
            )
        )

    for snapshot in sorted(snapshots or [], key=_record_priority, reverse=True):
        if not getattr(snapshot, "is_active", True):
            continue
        if str(getattr(snapshot, "layer", "") or "") == "candidate":
            continue
        memory_key = str(getattr(snapshot, "memory_key", "") or "")
        if memory_key.startswith(("pattern_candidate:", "automation_candidate:", "skill_draft:")):
            continue
        content = str(getattr(snapshot, "content", "") or "")
        lines = _snapshot_lines(content)
        if memory_key.startswith(("manual_note:", "knowledge_note:")):
            metadata = getattr(snapshot, "metadata", None) or {}
            playbook_summary = _summarize_operational_playbook(str(snapshot.title), content, metadata=metadata)
            if playbook_summary:
                playbooks.append(
                    _with_provenance(
                        playbook_summary,
                        metadata=metadata,
                        confidence=float(snapshot.confidence or 0.85),
                        last_verified_at=snapshot.last_verified_at,
                        source_kind=snapshot.source_kind,
                        source_ref=snapshot.source_ref,
                    )
                )
                continue
            records.append(
                MemoryRecord(
                    domain=str(metadata.get("category") or "manual"),
                    title=str(snapshot.title),
                    content=compact_text(content, limit=240),
                    confidence=float(snapshot.confidence or 0.85),
                    freshness_score=compute_freshness_score(snapshot.updated_at, snapshot.last_verified_at),
                    last_verified_at=snapshot.last_verified_at.isoformat() if snapshot.last_verified_at else None,
                    metadata=dict(metadata) | {"version": snapshot.version, "manual": True},
                )
            )
            continue
        if memory_key in {"profile", "access"}:
            stable_facts.extend(
                _with_provenance(
                    line,
                    metadata=getattr(snapshot, "metadata", None) or {},
                    confidence=float(snapshot.confidence or 0.8),
                    last_verified_at=snapshot.last_verified_at,
                    source_kind=snapshot.source_kind,
                    source_ref=snapshot.source_ref,
                )
                for line in lines
            )
        elif memory_key == "risks":
            known_risks.extend(
                _with_provenance(
                    line,
                    metadata=getattr(snapshot, "metadata", None) or {},
                    confidence=float(snapshot.confidence or 0.8),
                    last_verified_at=snapshot.last_verified_at,
                    source_kind=snapshot.source_kind,
                    source_ref=snapshot.source_ref,
                )
                for line in lines
            )
        elif memory_key == "recent_changes":
            recent_changes.extend(
                _with_provenance(
                    line,
                    metadata=getattr(snapshot, "metadata", None) or {},
                    confidence=float(snapshot.confidence or 0.8),
                    last_verified_at=snapshot.last_verified_at,
                    source_kind=snapshot.source_kind,
                    source_ref=snapshot.source_ref,
                )
                for line in lines
            )
        else:
            records.append(
                MemoryRecord(
                    domain=memory_key,
                    title=str(snapshot.title),
                    content=compact_text(content, limit=260),
                    confidence=float(snapshot.confidence or 0.8),
                    freshness_score=compute_freshness_score(snapshot.updated_at, snapshot.last_verified_at),
                    last_verified_at=snapshot.last_verified_at.isoformat() if snapshot.last_verified_at else None,
                    metadata=(getattr(snapshot, "metadata", None) or {}) | {"version": snapshot.version},
                )
            )

    for item in list(revalidations or [])[:4]:
        incidents.append(
            _with_provenance(
                f"Требует перепроверки: {item.title} — {compact_text(item.reason, limit=180)}",
                metadata={"trust_level": "stale", "verification_status": "needs_revalidation"},
                confidence=float(item.confidence or 0.4),
                source_kind="revalidation",
                source_ref=f"revalidation:{item.id}",
            )
        )

    for item in list(episodes or [])[:6]:
        summary = _clean_episode_summary(str(getattr(item, "summary", "") or ""), limit=3)
        if not summary:
            continue
        if item.episode_kind == "incident":
            incidents.append(
                _with_provenance(
                    f"{item.title}: {summary}",
                    metadata=getattr(item, "metadata", None) or {},
                    confidence=float(item.confidence or 0.7),
                    source_kind=item.source_kind,
                    source_ref=item.source_ref,
                )
            )
        elif item.episode_kind in {"deploy_operation", "pipeline_operation"}:
            recent_changes.append(
                _with_provenance(
                    f"{item.title}: {summary}",
                    metadata=getattr(item, "metadata", None) or {},
                    confidence=float(item.confidence or 0.7),
                    source_kind=item.source_kind,
                    source_ref=item.source_ref,
                )
            )
        else:
            records.append(
                MemoryRecord(
                    domain=item.episode_kind,
                    title=str(item.title),
                    content=summary,
                    confidence=float(item.confidence or 0.7),
                    freshness_score=compute_freshness_score(item.updated_at),
                    metadata=(getattr(item, "metadata", None) or {}) | {"event_count": item.event_count},
                )
            )

    if latest_health:
        stable_facts.append(
            _with_provenance(
                f"Health: status={latest_health.status}, cpu={latest_health.cpu_percent}, mem={latest_health.memory_percent}, disk={latest_health.disk_percent}",
                metadata=_provenance_metadata(TRUST_SYSTEM_MEASURED, VERIFICATION_MEASURED),
                confidence=0.9,
                last_verified_at=latest_health.checked_at,
                source_kind="monitoring",
                source_ref=f"health:{latest_health.id}",
            )
        )

    for alert in list(active_alerts or [])[:4]:
        alert_metadata = _provenance_metadata(TRUST_SYSTEM_MEASURED, VERIFICATION_MEASURED, source_actor_kind="watcher")
        incidents.append(
            _with_provenance(
                f"[{alert.severity}] {alert.title}: {compact_text(alert.message, limit=180)}",
                metadata=alert_metadata,
                confidence=0.88,
                source_kind="monitoring",
                source_ref=f"alert:{alert.id}",
            )
        )
        known_risks.append(
            _with_provenance(
                f"Алерт {alert.alert_type}: {alert.title}",
                metadata=alert_metadata,
                confidence=0.88,
                source_kind="monitoring",
                source_ref=f"alert:{alert.id}",
            )
        )

    for run in list(recent_runs or [])[:3]:
        label = getattr(run.agent, "name", "Agent")
        snippet_source = run.final_report or run.ai_analysis or ""
        snippet = compact_text(" ".join(line for line in snippet_source.splitlines() if line.strip()), limit=150)
        recent_changes.append(
            _with_provenance(
                f"{label} ({run.status}) @ {run.started_at.isoformat()}: {snippet}",
                metadata=_provenance_metadata(TRUST_AGENT_REPORTED, VERIFICATION_UNVERIFIED, source_actor_kind="agent"),
                confidence=0.48,
                source_kind="agent_run",
                source_ref=f"agent-run:{run.id}",
            )
        )

    if not snapshots:
        for item in list(legacy_knowledge or [])[:6]:
            playbook_summary = _summarize_operational_playbook(
                str(item.title),
                str(item.content),
                metadata={"category": getattr(item, "category", "")},
            )
            if playbook_summary:
                playbooks.append(
                    _with_provenance(
                        playbook_summary,
                        metadata={
                            "category": getattr(item, "category", ""),
                            "source": getattr(item, "source", ""),
                            "trust_level": TRUST_MANUAL_VERIFIED if item.source == "manual" else TRUST_HUMAN_OBSERVED,
                            "verification_status": VERIFICATION_VERIFIED if item.source == "manual" else VERIFICATION_UNVERIFIED,
                            "source_actor_kind": "human",
                        },
                        confidence=float(item.confidence or 0.8),
                        last_verified_at=item.verified_at,
                        source_kind="manual_knowledge",
                        source_ref=f"knowledge:{item.id}",
                    )
                )
                continue
            records.append(
                MemoryRecord(
                    domain=item.category,
                    title=str(item.title),
                    content=compact_text(str(item.content), limit=220),
                    confidence=float(item.confidence or 0.8),
                    freshness_score=compute_freshness_score(item.updated_at, item.verified_at),
                    last_verified_at=item.verified_at.isoformat() if item.verified_at else None,
                    metadata={
                        "source": item.source,
                        "trust_level": TRUST_MANUAL_VERIFIED if item.source == "manual" else TRUST_HUMAN_OBSERVED,
                        "verification_status": VERIFICATION_VERIFIED if item.source == "manual" else VERIFICATION_UNVERIFIED,
                        "source_actor_kind": "human",
                    },
                )
            )

    records.sort(key=lambda record: record.confidence * record.freshness_score, reverse=True)
    confidence_values = [record.confidence * record.freshness_score for record in records]
    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.78

    return ServerMemoryCard(
        server_id=server.id,
        identity={
            "name": server.name,
            "host": server.host,
            "port": server.port,
            "username": server.username,
            "server_type": server.server_type,
            "group": server.group.name if server.group_id else "",
        },
        topology_tags=tags[:10],
        stable_facts=list(dict.fromkeys(stable_facts))[:8],
        recent_changes=list(dict.fromkeys(recent_changes))[:6],
        known_risks=list(dict.fromkeys(known_risks))[:8],
        recent_incidents=list(dict.fromkeys(incidents))[:6],
        operational_playbooks=list(dict.fromkeys(playbooks))[:4],
        verified_at=latest_health.checked_at.isoformat() if latest_health else None,
        confidence=confidence,
        records=records[:8],
    )


def render_server_cards_prompt(cards: list[ServerMemoryCard], *, max_cards: int = 3, max_records: int = 6) -> str:
    if not cards:
        return "Память по серверам пока пуста."
    return "\n\n---\n\n".join(card.as_prompt_block(max_records=max_records) for card in cards[:max_cards])
