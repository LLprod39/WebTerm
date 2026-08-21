"""Legacy manual knowledge reads over an already-authorized server scope."""

from __future__ import annotations

import hashlib
import re

from django.db.models import Q

from servers.models import ServerGroupKnowledge, ServerKnowledge

_TOKEN_RE = re.compile(r"[\w./:-]{3,}", re.UNICODE)


def legacy_knowledge_rows(
    *,
    query: str,
    server_ids: list[int],
    server_groups: dict[int, int],
    operational_only: bool,
) -> list[dict]:
    """Return manual legacy rows without resolving or broadening authorization."""
    if not server_ids:
        return []
    query_terms = list(dict.fromkeys(_TOKEN_RE.findall(str(query or "").casefold())))[:8]
    if not query_terms:
        return []
    filters = Q(pk__in=[])
    for term in query_terms:
        filters |= Q(content__icontains=term) | Q(title__icontains=term)
    rows: list[dict] = []
    server_qs = ServerKnowledge.objects.filter(
        filters,
        server_id__in=server_ids,
        source="manual",
        is_active=True,
    )
    if operational_only:
        server_qs = server_qs.filter(_operational_knowledge_q(group_scope=False))
    for item in server_qs.order_by("id"):
        rows.append(
            {
                "source_type": "server_knowledge",
                "object_id": item.id,
                "server_id": item.server_id,
                "title": item.title,
                "content": item.content,
                "content_hash": _content_hash(item.content),
                "kind": item.category,
            }
        )

    authorized_group_ids = sorted(set(server_groups.values()))
    if not authorized_group_ids:
        return rows
    first_server_for_group = {
        group_id: min(server_id for server_id, current_group_id in server_groups.items() if current_group_id == group_id)
        for group_id in authorized_group_ids
    }
    group_qs = ServerGroupKnowledge.objects.filter(
        filters,
        group_id__in=authorized_group_ids,
        source="manual",
        is_active=True,
    )
    if operational_only:
        group_qs = group_qs.filter(_operational_knowledge_q(group_scope=True))
    for item in group_qs.order_by("id"):
        rows.append(
            {
                "source_type": "group_knowledge",
                "object_id": item.id,
                "server_id": first_server_for_group[item.group_id],
                "title": item.title,
                "content": item.content,
                "content_hash": _content_hash(item.content),
                "kind": item.category,
            }
        )
    return rows


def _content_hash(content: str) -> str:
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def _operational_knowledge_q(*, group_scope: bool) -> Q:
    categories = ["deployment", "monitoring", "backup"] if group_scope else ["services", "solutions"]
    return (
        Q(category__in=categories)
        | Q(title__istartswith="Operational Skill:")
        | Q(content__icontains="workflow:")
        | Q(content__icontains="связанный skill:")
    )
