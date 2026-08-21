"""Read-only scoped server-memory search endpoint."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core_ui.decorators import require_feature
from servers.models import ServerAgent
from servers.services.memory_asset_retrieval import (
    SAFE_ASSET_KINDS,
    SAFE_LEGACY_MEMORY_KEYS,
    memory_asset_retrieval_enabled,
    retrieve_server_memory,
)


@login_required
@require_feature("servers")
@require_POST
def server_memory_search(request, server_id: int):
    if not memory_asset_retrieval_enabled():
        return JsonResponse({"success": False, "error": "Not found"}, status=404)

    try:
        data = json.loads(request.body or "{}")
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    query = str(data.get("query") or "").strip()
    if not query:
        return JsonResponse({"success": False, "error": "Query is required"}, status=400)
    if len(query) > 1_000:
        return JsonResponse({"success": False, "error": "Query is too long"}, status=400)

    agent = None
    raw_agent_id = data.get("agent_id")
    if raw_agent_id not in {None, ""}:
        try:
            agent_id = int(raw_agent_id)
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "error": "Invalid agent scope"}, status=403)
        agent = ServerAgent.objects.filter(pk=agent_id, user=request.user).first()
        if agent is None:
            return JsonResponse({"success": False, "error": "Invalid agent scope"}, status=403)

    asset_kinds = data.get("asset_kinds")
    if asset_kinds is not None and (
        not isinstance(asset_kinds, list) or any(str(value) not in SAFE_ASSET_KINDS for value in asset_kinds)
    ):
        return JsonResponse({"success": False, "error": "Invalid asset kinds"}, status=400)
    legacy_keys = data.get("legacy_memory_keys")
    if legacy_keys is not None and (
        not isinstance(legacy_keys, list) or any(str(value) not in SAFE_LEGACY_MEMORY_KEYS for value in legacy_keys)
    ):
        return JsonResponse({"success": False, "error": "Invalid legacy keys"}, status=400)

    result = retrieve_server_memory(
        user=request.user,
        query=query,
        server_ids=[server_id],
        agent=agent,
        include_candidates=False,
        asset_kinds=asset_kinds,
        legacy_memory_keys=legacy_keys,
        include_legacy_knowledge=True,
        top_k=data.get("top_k", 5),
        char_budget=data.get("char_budget", 4_000),
    )
    status_code = 403 if result.status == "denied" else 200
    return JsonResponse(
        {
            "success": result.status == "succeeded",
            "status": result.status,
            "query_sha256": result.query_sha256,
            "audit_id": result.audit_id,
            "items": [
                {
                    "ref": hit.ref,
                    "source_type": hit.source_type,
                    "kind": hit.kind,
                    "server_id": hit.server_id,
                    "title": hit.title,
                    "content": hit.content,
                    "content_hash": hit.content_hash,
                    "score": hit.score,
                }
                for hit in result.hits
            ],
        },
        status=status_code,
    )
