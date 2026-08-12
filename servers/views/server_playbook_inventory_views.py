"""Playbook inventory preview endpoint."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility
from servers.services.playbook_compatibility_inventory import (
    inventory_groups_from_bindings,
    normalize_inventory_bindings,
)
from servers.services.playbook_runner import build_inventory_for_servers, resolve_target_servers
from servers.views.server_playbook_serializers import _playbooks_for_user


@login_required
@require_feature("automation")
@require_http_methods(["POST"])
def playbook_inventory_preview(request):
    data = json.loads(request.body or "{}")
    server_ids = [int(x) for x in (data.get("server_ids") or []) if str(x).isdigit() or isinstance(x, int)]
    group_ids = [int(x) for x in (data.get("group_ids") or []) if str(x).isdigit() or isinstance(x, int)]
    servers = resolve_target_servers(request.user, server_ids=server_ids, group_ids=group_ids)
    selected_ids = {server.id for server in servers}
    normalized_bindings = normalize_inventory_bindings(data.get("inventory_bindings"))
    resolved_bindings: dict[str, list[int]] = {}
    for selector, binding in normalized_bindings.items():
        bound_servers = resolve_target_servers(
            request.user,
            server_ids=binding["server_ids"],
            group_ids=binding["group_ids"],
        )
        resolved_bindings[selector] = sorted(server.id for server in bound_servers if server.id in selected_ids)
    binding_groups = inventory_groups_from_bindings(resolved_bindings)
    inventory = build_inventory_for_servers(servers, extra_groups=binding_groups)
    compatibility = {}
    playbook_id = data.get("playbook_id")
    if str(playbook_id).isdigit():
        playbook = _playbooks_for_user(request.user).filter(id=int(playbook_id)).first()
        if playbook and playbook.source_yaml:
            analysis_source = (
                playbook.active_compatibility_revision.adapted_yaml
                if playbook.active_compatibility_revision
                and playbook.active_compatibility_revision.status == "validated"
                else playbook.source_yaml
            )
            analysis_bindings = {
                selector: {"server_ids": ids, "group_ids": []} for selector, ids in resolved_bindings.items()
            }
            compatibility = analyze_playbook_compatibility(
                analysis_source,
                bindings=analysis_bindings,
                target_servers=servers,
            )
    return JsonResponse(
        {
            "success": True,
            "inventory": inventory,
            "hosts": [
                {
                    "id": server.id,
                    "name": server.name,
                    "host": server.host,
                    "port": server.port,
                    "username": server.username,
                    "group_id": server.group_id,
                    "detected_os": getattr(server, "detected_os", "") or "",
                }
                for server in servers
            ],
            "count": len(servers),
            "compatibility": compatibility,
            "inventory_bindings": normalized_bindings,
        }
    )
