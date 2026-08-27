"""Scoped deterministic lexical retrieval for server memory assets."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from django.conf import settings

from core_ui.projects import active_project_for_user
from servers.models import (
    ServerMemoryAsset,
    ServerMemoryAssetAgentBinding,
    ServerMemoryRetrievalAudit,
    ServerMemorySnapshot,
)
from servers.services.memory_asset_access import accessible_memory_assets_queryset, asset_is_consistent
from servers.services.memory_asset_legacy import legacy_knowledge_rows
from servers.services.server_query import CAPABILITY_VIEW_CONTEXT, get_servers_for_user_capability

FEATURE_FLAG_SETTING = "SERVER_MEMORY_ASSET_RETRIEVAL_ENABLED"
MAX_TOP_K = 50
MAX_CHAR_BUDGET = 50_000
SAFE_ASSET_KINDS = frozenset(choice[0] for choice in ServerMemoryAsset.KIND_CHOICES)
SAFE_LEGACY_MEMORY_KEYS = frozenset({"runbook", "human_habits"})
OPERATIONAL_ASSET_KINDS = frozenset(
    {
        ServerMemoryAsset.KIND_RUNBOOK,
        ServerMemoryAsset.KIND_DECISION,
        ServerMemoryAsset.KIND_PATTERN,
    }
)
OPERATIONAL_LEGACY_MEMORY_KEYS = frozenset({"runbook", "human_habits"})
_TOKEN_RE = re.compile(r"[\w./:-]+", re.UNICODE)


@dataclass(frozen=True)
class MemoryRetrievalHit:
    source_type: str
    object_id: int
    snapshot_id: int | None
    server_id: int
    title: str
    content: str
    content_hash: str
    score: int
    injection_mode: str = ""
    kind: str = ""

    @property
    def ref(self) -> str:
        if self.snapshot_id is None:
            return f"{self.source_type}:{self.object_id}"
        return f"{self.source_type}:{self.object_id}:snapshot:{self.snapshot_id}"


@dataclass(frozen=True)
class MemoryRetrievalResult:
    hits: tuple[MemoryRetrievalHit, ...]
    audit_id: int | None
    query_sha256: str
    status: str


def memory_asset_retrieval_enabled() -> bool:
    """Future integration gate; default-off without editing environment files."""
    return bool(getattr(settings, FEATURE_FLAG_SETTING, False))


def retrieve_server_memory(
    *,
    user,
    query: str,
    server_ids: list[int] | tuple[int, ...] | None = None,
    agent=None,
    include_candidates: bool = False,
    asset_kinds: list[str] | tuple[str, ...] | set[str] | None = None,
    legacy_memory_keys: list[str] | tuple[str, ...] | set[str] | None = None,
    include_legacy_knowledge: bool = False,
    operational_only: bool = False,
    top_k: int = 5,
    char_budget: int = 4_000,
) -> MemoryRetrievalResult:
    """Return scoped results, failing safe to an empty audited result."""
    started = perf_counter()
    query_hash = _query_hash(query)
    requested_ids = _normalize_server_ids(server_ids)
    normalized_top_k = _bounded_int(top_k, default=5, lower=1, upper=MAX_TOP_K)
    normalized_budget = _bounded_int(char_budget, default=4_000, lower=0, upper=MAX_CHAR_BUDGET)
    normalized_asset_kinds = _normalize_safe_filter(asset_kinds, allowed=SAFE_ASSET_KINDS)
    normalized_legacy_keys = _normalize_safe_filter(legacy_memory_keys, allowed=SAFE_LEGACY_MEMORY_KEYS)
    try:
        return _retrieve_scoped(
            user=user,
            query=str(query or ""),
            query_hash=query_hash,
            requested_ids=requested_ids,
            server_scope_was_explicit=server_ids is not None,
            agent=agent,
            include_candidates=bool(include_candidates),
            asset_kinds=normalized_asset_kinds,
            legacy_memory_keys=normalized_legacy_keys,
            include_legacy_knowledge=bool(include_legacy_knowledge),
            operational_only=bool(operational_only),
            top_k=normalized_top_k,
            char_budget=normalized_budget,
            started=started,
        )
    except Exception:
        audit = _write_audit_safe(
            user=user,
            project=_safe_active_project(user),
            agent=agent,
            query_hash=query_hash,
            status=ServerMemoryRetrievalAudit.STATUS_ERROR,
            include_candidates=bool(include_candidates),
            requested_server_count=len(requested_ids),
            accessible_server_count=0,
            result_refs=[],
            returned_char_count=0,
            top_k=normalized_top_k,
            char_budget=normalized_budget,
            duration_ms=_elapsed_ms(started),
            error_code="retrieval_service_error",
        )
        return MemoryRetrievalResult(
            hits=(),
            audit_id=getattr(audit, "pk", None),
            query_sha256=query_hash,
            status=ServerMemoryRetrievalAudit.STATUS_ERROR,
        )


def _retrieve_scoped(
    *,
    user,
    query: str,
    query_hash: str,
    requested_ids: list[int],
    server_scope_was_explicit: bool,
    agent,
    include_candidates: bool,
    asset_kinds: set[str] | None,
    legacy_memory_keys: set[str] | None,
    include_legacy_knowledge: bool,
    operational_only: bool,
    top_k: int,
    char_budget: int,
    started: float,
) -> MemoryRetrievalResult:
    project = active_project_for_user(user)
    if not getattr(user, "is_authenticated", False):
        return _denied_result(
            user=user,
            project=project,
            agent=agent,
            query_hash=query_hash,
            requested_ids=requested_ids,
            include_candidates=include_candidates,
            top_k=top_k,
            char_budget=char_budget,
            started=started,
        )
    if agent is not None and agent.user_id != user.pk:
        return _denied_result(
            user=user,
            project=project,
            agent=agent,
            query_hash=query_hash,
            requested_ids=requested_ids,
            include_candidates=include_candidates,
            top_k=top_k,
            char_budget=char_budget,
            started=started,
        )

    authorized_servers = get_servers_for_user_capability(user, CAPABILITY_VIEW_CONTEXT)
    if server_scope_was_explicit:
        authorized_servers = authorized_servers.filter(pk__in=requested_ids)
    if agent is not None:
        authorized_servers = authorized_servers.filter(agents=agent)
    if include_candidates:
        if not getattr(user, "is_staff", False):
            return _denied_result(
                user=user,
                project=project,
                agent=agent,
                query_hash=query_hash,
                requested_ids=requested_ids,
                include_candidates=include_candidates,
                top_k=top_k,
                char_budget=char_budget,
                started=started,
            )
        authorized_servers = authorized_servers.filter(user=user)
    accessible_ids = list(authorized_servers.order_by("pk").values_list("pk", flat=True).distinct())
    accessible_project_ids = list(authorized_servers.order_by().values_list("project_id", flat=True).distinct()[:2])
    audit_project = agent.project if agent is not None else None
    if audit_project is None and len(accessible_project_ids) == 1:
        audit_project = authorized_servers.first().project
    if server_scope_was_explicit and requested_ids and not accessible_ids:
        return _denied_result(
            user=user,
            project=project,
            agent=agent,
            query_hash=query_hash,
            requested_ids=requested_ids,
            include_candidates=include_candidates,
            top_k=top_k,
            char_budget=char_budget,
            started=started,
        )

    lifecycles = [ServerMemoryAsset.LIFECYCLE_APPROVED]
    if include_candidates:
        lifecycles.append(ServerMemoryAsset.LIFECYCLE_CANDIDATE)
    asset_rows = list(
        accessible_memory_assets_queryset(
            user=user,
            server_ids=accessible_ids,
            agent=agent,
        )
        .filter(lifecycle__in=lifecycles, current_snapshot__isnull=False)
        .select_related("current_snapshot")
        .order_by("id")
    )
    if asset_kinds is not None:
        asset_rows = [asset for asset in asset_rows if asset.asset_kind in asset_kinds]
    bindings_by_asset: dict[int, ServerMemoryAssetAgentBinding] = {}
    if agent is not None and asset_rows:
        bindings_by_asset = {
            binding.asset_id: binding
            for binding in ServerMemoryAssetAgentBinding.objects.filter(
                asset_id__in=[asset.id for asset in asset_rows],
                agent=agent,
                enabled=True,
            ).select_related("pinned_snapshot")
        }

    scored: list[MemoryRetrievalHit] = []
    for asset in asset_rows:
        if not asset_is_consistent(asset):
            continue
        binding = bindings_by_asset.get(asset.id)
        snapshot = binding.pinned_snapshot if binding and binding.pinned_snapshot_id else asset.current_snapshot
        if snapshot is None or snapshot.server_id != asset.server_id or snapshot.asset_id != asset.id:
            continue
        if (binding is None or binding.pinned_snapshot_id is None) and (
            not snapshot.is_active or snapshot.archived_at is not None
        ):
            continue
        if not include_candidates and snapshot.layer != ServerMemorySnapshot.LAYER_CANONICAL:
            continue
        if include_candidates and snapshot.layer not in {
            ServerMemorySnapshot.LAYER_CANONICAL,
            ServerMemorySnapshot.LAYER_CANDIDATE,
        }:
            continue
        score = _lexical_score(query, asset.title, snapshot.content)
        if score > 0:
            scored.append(
                MemoryRetrievalHit(
                    source_type="asset",
                    object_id=asset.id,
                    snapshot_id=snapshot.id,
                    server_id=asset.server_id,
                    title=asset.title,
                    content=snapshot.content,
                    content_hash=snapshot.content_hash,
                    score=score,
                    injection_mode=binding.injection_mode if binding else "",
                    kind=asset.asset_kind,
                )
            )

    legacy_rows = ServerMemorySnapshot.objects.filter(
        server_id__in=accessible_ids,
        asset__isnull=True,
        is_active=True,
        archived_at__isnull=True,
    )
    if include_candidates:
        legacy_rows = legacy_rows.filter(
            layer__in=[ServerMemorySnapshot.LAYER_CANONICAL, ServerMemorySnapshot.LAYER_CANDIDATE]
        )
    else:
        legacy_rows = legacy_rows.filter(layer=ServerMemorySnapshot.LAYER_CANONICAL)
    if legacy_memory_keys is not None:
        legacy_rows = legacy_rows.filter(memory_key__in=legacy_memory_keys)
    for snapshot in legacy_rows.only("id", "server_id", "memory_key", "title", "content", "content_hash").order_by(
        "id"
    ):
        score = _lexical_score(query, snapshot.title, snapshot.content)
        if score > 0:
            scored.append(
                MemoryRetrievalHit(
                    source_type="legacy_snapshot",
                    object_id=snapshot.id,
                    snapshot_id=snapshot.id,
                    server_id=snapshot.server_id,
                    title=snapshot.title,
                    content=snapshot.content,
                    content_hash=snapshot.content_hash,
                    score=score,
                    kind=snapshot.memory_key,
                )
            )

    if include_legacy_knowledge:
        server_groups = dict(authorized_servers.filter(group_id__isnull=False).values_list("id", "group_id").distinct())
        for row in legacy_knowledge_rows(
            query=query,
            server_ids=accessible_ids,
            server_groups=server_groups,
            operational_only=operational_only,
        ):
            score = _lexical_score(query, row["title"], row["content"])
            if score <= 0:
                continue
            scored.append(
                MemoryRetrievalHit(
                    source_type=row["source_type"],
                    object_id=row["object_id"],
                    snapshot_id=None,
                    server_id=row["server_id"],
                    title=row["title"],
                    content=row["content"],
                    content_hash=row["content_hash"],
                    score=score,
                    kind=row["kind"],
                )
            )

    scored.sort(key=lambda hit: (-hit.score, hit.server_id, hit.source_type, hit.object_id, hit.snapshot_id or 0))
    hits = _apply_budget(scored, top_k=top_k, char_budget=char_budget)
    audit = _write_audit_safe(
        user=user,
        project=audit_project,
        agent=agent,
        query_hash=query_hash,
        status=ServerMemoryRetrievalAudit.STATUS_SUCCEEDED,
        include_candidates=include_candidates,
        requested_server_count=len(requested_ids),
        accessible_server_count=len(accessible_ids),
        result_refs=[hit.ref for hit in hits],
        returned_char_count=sum(len(hit.content) for hit in hits),
        top_k=top_k,
        char_budget=char_budget,
        duration_ms=_elapsed_ms(started),
    )
    return MemoryRetrievalResult(
        hits=tuple(hits),
        audit_id=getattr(audit, "pk", None),
        query_sha256=query_hash,
        status=ServerMemoryRetrievalAudit.STATUS_SUCCEEDED,
    )


def _denied_result(
    *,
    user,
    project,
    agent,
    query_hash: str,
    requested_ids: list[int],
    include_candidates: bool,
    top_k: int,
    char_budget: int,
    started: float,
) -> MemoryRetrievalResult:
    audit = _write_audit_safe(
        user=user,
        project=project,
        agent=agent,
        query_hash=query_hash,
        status=ServerMemoryRetrievalAudit.STATUS_DENIED,
        include_candidates=include_candidates,
        requested_server_count=len(requested_ids),
        accessible_server_count=0,
        result_refs=[],
        returned_char_count=0,
        top_k=top_k,
        char_budget=char_budget,
        duration_ms=_elapsed_ms(started),
        error_code="memory_scope_denied",
    )
    return MemoryRetrievalResult(
        hits=(),
        audit_id=getattr(audit, "pk", None),
        query_sha256=query_hash,
        status=ServerMemoryRetrievalAudit.STATUS_DENIED,
    )


def _write_audit_safe(
    *,
    user,
    project,
    agent,
    query_hash: str,
    status: str,
    include_candidates: bool,
    requested_server_count: int,
    accessible_server_count: int,
    result_refs: list[str],
    returned_char_count: int,
    top_k: int,
    char_budget: int,
    duration_ms: int,
    error_code: str = "",
):
    try:
        return ServerMemoryRetrievalAudit.objects.create(
            user_id=getattr(user, "pk", None),
            project_id=getattr(project, "pk", None),
            agent_id=getattr(agent, "pk", None),
            query_sha256=query_hash,
            status=status,
            include_candidates=include_candidates,
            requested_server_count=max(0, int(requested_server_count)),
            accessible_server_count=max(0, int(accessible_server_count)),
            result_count=len(result_refs),
            returned_char_count=max(0, int(returned_char_count)),
            requested_top_k=top_k,
            requested_char_budget=char_budget,
            result_refs=[str(ref)[:96] for ref in result_refs[:MAX_TOP_K]],
            error_code=str(error_code or "")[:80],
            duration_ms=max(0, int(duration_ms)),
        )
    except Exception:
        return None


def _lexical_score(query: str, title: str, content: str) -> int:
    normalized_query = " ".join(str(query or "").casefold().split())
    query_tokens = set(_TOKEN_RE.findall(normalized_query))
    if not query_tokens:
        return 0
    normalized_title = str(title or "").casefold()
    normalized_content = str(content or "").casefold()
    title_tokens = set(_TOKEN_RE.findall(normalized_title))
    content_tokens = set(_TOKEN_RE.findall(normalized_content))
    score = 4 * len(query_tokens & title_tokens) + len(query_tokens & content_tokens)
    if normalized_query in normalized_title:
        score += 8
    if normalized_query in normalized_content:
        score += 3
    return score


def _apply_budget(scored: list[MemoryRetrievalHit], *, top_k: int, char_budget: int) -> list[MemoryRetrievalHit]:
    if char_budget <= 0:
        return []
    remaining = char_budget
    selected: list[MemoryRetrievalHit] = []
    for hit in scored:
        if len(selected) >= top_k or remaining <= 0:
            break
        clipped_content = hit.content[:remaining]
        if not clipped_content:
            continue
        selected.append(
            MemoryRetrievalHit(
                source_type=hit.source_type,
                object_id=hit.object_id,
                snapshot_id=hit.snapshot_id,
                server_id=hit.server_id,
                title=hit.title,
                content=clipped_content,
                content_hash=hit.content_hash,
                score=hit.score,
                injection_mode=hit.injection_mode,
                kind=hit.kind,
            )
        )
        remaining -= len(clipped_content)
    return selected


def _query_hash(query: Any) -> str:
    return hashlib.sha256(str(query or "").encode("utf-8")).hexdigest()


def _normalize_server_ids(values) -> list[int]:
    normalized: list[int] = []
    for value in values or []:
        try:
            server_id = int(value)
        except (TypeError, ValueError):
            continue
        if server_id > 0 and server_id not in normalized:
            normalized.append(server_id)
    return normalized


def _normalize_safe_filter(values, *, allowed: frozenset[str]) -> set[str] | None:
    if values is None:
        return None
    return {str(value).strip() for value in values if str(value).strip() in allowed}


def _bounded_int(value: Any, *, default: int, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(parsed, upper))


def _safe_active_project(user):
    try:
        return active_project_for_user(user)
    except Exception:
        return None


def _elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))
