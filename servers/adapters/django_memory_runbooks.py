from __future__ import annotations

import re
from typing import Any

from django.db.models import Q
from django.utils import timezone

from app.agent_kernel.memory.compaction import compact_text, unique_preserving_order
from app.agent_kernel.memory.trust import prompt_provenance_label
from app.agent_kernel.memory.types import AUTOMATION_CANDIDATE_PREFIX, PATTERN_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX


def search_runbooks(query: str, *, server_id: int | None = None, group_id: int | None = None) -> list[dict]:
    from servers.models import ServerGroupKnowledge, ServerKnowledge, ServerMemorySnapshot

    query = str(query or "").strip()
    if not query:
        return []
    query_lower = query.lower()
    items: list[dict] = []
    filters = Q(content__icontains=query) | Q(title__icontains=query)
    if server_id is not None:
        for item in ServerMemorySnapshot.objects.filter(
            filters,
            server_id=server_id,
            is_active=True,
            layer=ServerMemorySnapshot.LAYER_CANONICAL,
        ).order_by("-updated_at")[:12]:
            memory_key = str(item.memory_key or "")
            metadata = dict(item.metadata or {})
            include_manual_operational = memory_key.startswith(("manual_note:", "knowledge_note:")) and (
                str(metadata.get("category") or "").strip().lower() in {"solutions", "services"}
                or str(item.title or "").lower().startswith("operational skill:")
                or "workflow:" in str(item.content or "").lower()
                or "связанный skill:" in str(item.content or "").lower()
            )
            if memory_key not in {"runbook", "human_habits"} and not include_manual_operational:
                continue
            if memory_key.startswith((PATTERN_CANDIDATE_PREFIX, AUTOMATION_CANDIDATE_PREFIX, SKILL_DRAFT_PREFIX)):
                continue
            items.append(
                {
                    "scope": "server",
                    "title": item.title,
                    "content": compact_text(item.content, limit=240),
                    "category": metadata.get("category") or item.memory_key,
                    "memory_key": item.memory_key,
                    "metadata": metadata,
                    "confidence": float(item.confidence or 0.0),
                    "source_kind": item.source_kind,
                    "source_ref": item.source_ref,
                    "last_verified_at": item.last_verified_at,
                    "_score": runbook_match_score(
                        query_lower,
                        title=str(item.title or ""),
                        content=str(item.content or ""),
                        metadata=metadata,
                    ),
                    "_updated_at": getattr(item, "updated_at", None),
                }
            )
        if not items:
            for item in ServerKnowledge.objects.filter(filters, server_id=server_id, is_active=True).order_by(
                "-updated_at"
            )[:6]:
                items.append(
                    {
                        "scope": "server",
                        "title": item.title,
                        "content": compact_text(item.content, limit=240),
                        "category": item.category,
                        "memory_key": f"knowledge:{item.id}",
                        "metadata": {
                            "category": item.category,
                            "trust_level": "manual_verified" if item.source == "manual" else "human_observed",
                            "verification_status": "verified" if item.source == "manual" else "unverified",
                            "source_actor_kind": "human",
                        },
                        "confidence": float(item.confidence or 0.0),
                        "source_kind": "manual_knowledge",
                        "source_ref": f"knowledge:{item.id}",
                        "last_verified_at": item.verified_at,
                        "_score": runbook_match_score(
                            query_lower,
                            title=str(item.title or ""),
                            content=str(item.content or ""),
                            metadata={"category": item.category},
                        ),
                        "_updated_at": getattr(item, "updated_at", None),
                    }
                )
    if group_id is not None:
        for item in ServerGroupKnowledge.objects.filter(filters, group_id=group_id, is_active=True).order_by(
            "-updated_at"
        )[:6]:
            items.append(
                {
                    "scope": "group",
                    "title": item.title,
                    "content": compact_text(item.content, limit=240),
                    "category": item.category,
                    "memory_key": f"group_knowledge:{item.id}",
                    "metadata": {"category": item.category},
                    "confidence": float(item.confidence or 0.0),
                    "source_kind": "group_knowledge",
                    "source_ref": f"group_knowledge:{item.id}",
                    "_score": runbook_match_score(
                        query_lower,
                        title=str(item.title or ""),
                        content=str(item.content or ""),
                        metadata={"category": item.category},
                    ),
                    "_updated_at": getattr(item, "updated_at", None),
                }
            )
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in sorted(
        items,
        key=lambda entry: (
            float(entry.get("_score") or 0.0),
            entry.get("_updated_at") or timezone.now(),
        ),
        reverse=True,
    ):
        key = (
            str(item.get("scope") or ""),
            str(item.get("title") or ""),
            str(item.get("content") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        item.pop("_score", None)
        item.pop("_updated_at", None)
        deduped.append(item)
    return deduped[:8]


def build_operational_recipes_prompt(
    query: str,
    *,
    server_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    limit: int = 5,
) -> str:
    query_terms = extract_runbook_query_terms(query)
    if not query_terms:
        return "- Нет релевантных operational recipes."

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for server_id in list(server_ids or [])[:3]:
        for term in query_terms:
            for item in search_runbooks(term, server_id=server_id):
                key = (str(item.get("scope") or ""), str(item.get("title") or ""), str(item.get("content") or ""))
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)

    for group_id in list(group_ids or [])[:3]:
        for term in query_terms:
            for item in search_runbooks(term, group_id=group_id):
                key = (str(item.get("scope") or ""), str(item.get("title") or ""), str(item.get("content") or ""))
                if key in seen:
                    continue
                seen.add(key)
                items.append(item)

    if not items:
        return "- Нет релевантных operational recipes."

    lines = []
    for item in items[: max(1, min(int(limit), 8))]:
        lines.append(format_operational_recipe_prompt_item(item))
    return "\n".join(lines)


def format_operational_recipe_prompt_item(item: dict[str, Any]) -> str:
    scope = str(item.get("scope") or "server")
    category = str(item.get("category") or "runbook")
    title = compact_text(str(item.get("title") or ""), limit=120)
    content = compact_text(str(item.get("content") or ""), limit=220)
    metadata = dict(item.get("metadata") or {})
    provenance = prompt_provenance_label(
        metadata=metadata,
        confidence=float(item.get("confidence") or 0.0),
        last_verified_at=item.get("last_verified_at"),
        source_kind=str(item.get("source_kind") or ""),
        source_ref=str(item.get("source_ref") or ""),
    )
    detail_parts: list[str] = [f"{provenance} [{scope}/{category}] {title}: {content}"]
    for label, key, limit in (
        ("Use", "when_to_use", 140),
        ("Recipe", "playbook_summary", 160),
        ("Verify", "verification", 140),
        ("Rollback", "rollback_hint", 140),
        ("Attach", "runtime_attachment", 140),
    ):
        value = compact_text(str(metadata.get(key) or ""), limit=limit)
        if value:
            detail_parts.append(f"{label}={value}")
    risk_level = compact_text(str(metadata.get("risk_level") or ""), limit=40)
    if risk_level:
        detail_parts.append(f"Risk={risk_level}")
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and confidence > 0:
        detail_parts.append(f"Confidence={int(float(confidence) * 100)}%")
    return "- " + " | ".join(detail_parts[:7])


def extract_runbook_query_terms(query: str) -> list[str]:
    normalized = compact_text(str(query or "").replace("\n", " "), limit=240).strip()
    if not normalized:
        return []
    terms = unique_preserving_order([normalized], limit=1)
    token_candidates = re.findall(r"[A-Za-zА-Яа-яЁё0-9_./:-]{3,}", normalized.lower())
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "from",
        "into",
        "this",
        "need",
        "after",
        "что",
        "для",
        "после",
        "перед",
        "если",
        "или",
        "при",
        "это",
        "как",
        "без",
        "server",
        "agent",
        "роль",
        "server_id",
        "group_id",
    }
    for token in token_candidates:
        if token in stop_words:
            continue
        terms.append(token)
        if len(terms) >= 8:
            break
    return unique_preserving_order(terms, limit=8)


def runbook_match_score(query_lower: str, *, title: str, content: str, metadata: dict[str, Any] | None = None) -> float:
    metadata = metadata or {}
    haystacks = [
        str(title or "").lower(),
        str(content or "").lower(),
        str(metadata.get("intent") or "").lower(),
        str(metadata.get("intent_label") or "").lower(),
        str(metadata.get("display_command") or "").lower(),
        " ".join(str(item).lower() for item in (metadata.get("commands") or []) if str(item).strip()),
    ]
    score = 0.0
    if haystacks[0] and query_lower in haystacks[0]:
        score += 3.0
    if haystacks[1] and query_lower in haystacks[1]:
        score += 2.0
    if any(query_lower in haystack for haystack in haystacks[2:]):
        score += 1.5
    if str(metadata.get("category") or "").strip().lower() in {"solutions", "services"}:
        score += 0.4
    return score
