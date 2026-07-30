"""Inventory operator tools: list / resolve / info / fleet status (F-08a split)."""

from __future__ import annotations

from typing import Any

from app.assistant_actions import AssistantActionContext, AssistantActionError
from core_ui.access import feature_allowed_for_user
from servers.operator.tools_common import _int_arg, _server_for_user
from servers.operator.tools_hints import normalize_host_hint, server_matches_query
from servers.views.server_helpers import _accessible_servers_queryset


def _monitoring_rows_by_server_id(user) -> dict[int, dict[str, Any]]:
    """Same status resolution as dashboard/API (metrics + live cache, not raw last row)."""
    try:
        from servers.views.server_monitoring import _build_monitoring_status_payload

        payload = _build_monitoring_status_payload(user)
        rows = payload.get("servers") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return {}
        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = row.get("server_id")
            if sid is None:
                continue
            out[int(sid)] = row
        return out
    except Exception:  # noqa: BLE001
        return {}


def _server_row(s, mon_by_id: dict[int, dict[str, Any]], endpoint_counts: dict[str, int]) -> dict[str, Any]:
    key = f"{(s.host or '').strip().lower()}:{int(s.port or 22)}"
    mon = mon_by_id.get(int(s.id), {})
    status = str(mon.get("status") or "unknown")
    return {
        "id": s.id,
        "name": s.name,
        "host": s.host,
        "port": s.port,
        "os_family": getattr(s, "os_family", "") or "",
        "tags": [part.strip() for part in str(getattr(s, "tags", "") or "").split(",") if part.strip()],
        "ai_read_only": bool(getattr(s, "ai_read_only", False)),
        "status": status if status in {"healthy", "warning", "critical", "unreachable", "unknown"} else "unknown",
        "is_stale": bool(mon.get("is_stale")),
        "cpu_percent": mon.get("cpu_percent"),
        "memory_percent": mon.get("memory_percent"),
        "disk_percent": mon.get("disk_percent"),
        "shared_endpoint_count": endpoint_counts.get(key, 1),
        "terminal_url": f"/servers/{s.id}/terminal",
    }


def list_servers(ctx: AssistantActionContext) -> dict[str, Any]:
    """List or filter inventory.

    UX rules:
    - show_in_chat=true → interactive «Серверы» card (set by loop only for «покажи список»).
    - Default / lookup → no card. Prefer resolve_server for a named host.
    - Operator loop injects show_in_chat + q from the user message so the model cannot spam the fleet card.
    """
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    q = str(payload.get("q") or payload.get("name") or payload.get("query") or "").strip()

    # Default OFF — card only when explicitly requested (policy layer sets this for list intents).
    if "show_in_chat" in payload:
        show_in_chat = bool(payload.get("show_in_chat"))
    elif "ui_table" in payload:
        show_in_chat = bool(payload.get("ui_table"))
    else:
        show_in_chat = False

    all_servers = list(_accessible_servers_queryset(ctx.user).order_by("name")[:300])
    mon_by_id = _monitoring_rows_by_server_id(ctx.user)

    endpoint_counts: dict[str, int] = {}
    for s in all_servers:
        key = f"{(s.host or '').strip().lower()}:{int(s.port or 22)}"
        endpoint_counts[key] = endpoint_counts.get(key, 0) + 1

    # Full name→id map always (survives truncation better when placed first in payload)
    full_name_index = {str(s.name): int(s.id) for s in all_servers if getattr(s, "name", None)}

    qs = all_servers
    if q:
        qs = [s for s in all_servers if server_matches_query(s, q)]

    servers: list[dict[str, Any]] = []
    status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0}
    for s in qs[:100]:
        row = _server_row(s, mon_by_id, endpoint_counts)
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        servers.append(row)

    # Lookup with silent flag and no q was never intended — always emit rows for card or filter.
    emit_rows = show_in_chat or bool(q)
    if not emit_rows:
        status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0}
        for s in all_servers:
            mon = mon_by_id.get(int(s.id), {})
            st = str(mon.get("status") or "unknown")
            if st not in status_counts:
                st = "unknown"
            status_counts[st] = status_counts.get(st, 0) + 1
        servers = []

    unique_endpoints = len(
        {f"{(s.host or '').strip().lower()}:{int(s.port or 22)}" for s in (qs if emit_rows else all_servers)}
    )
    # Model-only notes (never shown in the chat card — use ui_note for humans).
    model_notes: list[str] = []
    ui_notes: list[str] = []
    if q:
        model_notes.append(f"Filtered by q={q!r}: {len(servers)} match(es).")
    if show_in_chat:
        model_notes.append(
            "Interactive inventory card is shown in chat. "
            "Reply with ONE short line only (count + status summary). "
            "Do NOT list host names or invent role descriptions — the UI card has them."
        )
    else:
        model_notes.append("UI card suppressed (lookup mode). For a named host prefer operator.resolve_server(q=…).")
    if not emit_rows:
        model_notes.append(f"Compact inventory: {len(full_name_index)} name(s) in name_index only (no server rows).")
    if unique_endpoints and unique_endpoints < len(all_servers if not emit_rows else servers or all_servers):
        mirror = f"{len(all_servers)} inventory rows map to {unique_endpoints} physical host:port endpoint(s)."
        model_notes.append(mirror)
        if show_in_chat:
            ui_notes.append(mirror)

    # name_index first so truncation of tool JSON keeps ids for every host (incl. lunix).
    return {
        "name_index": full_name_index if not q else {str(s["name"]): int(s["id"]) for s in servers if s.get("name")},
        "count": len(full_name_index) if not emit_rows else len(servers),
        "query": q or None,
        "servers": servers,
        "unique_endpoints": unique_endpoints,
        "status_counts": status_counts,
        "note": " ".join(model_notes) if model_notes else None,
        "ui_note": " ".join(ui_notes) if ui_notes else None,
        "reply_hint": (
            "UI card attached. Answer ≤1 sentence with counts only. Zero host-name bullets." if show_in_chat else None
        ),
        "ui_table": show_in_chat,
        "default_expanded": False,
        "target_url": "/servers",
    }


def resolve_server(ctx: AssistantActionContext) -> dict[str, Any]:
    """Resolve one host by name/host/id for connect/SSH — no inventory card in chat."""
    q = str(
        ctx.input_payload.get("q")
        or ctx.input_payload.get("name")
        or ctx.input_payload.get("server")
        or ctx.input_payload.get("host")
        or ""
    ).strip()
    if not q:
        raise AssistantActionError("q or name is required (e.g. lunix)")

    qs = list(_accessible_servers_queryset(ctx.user).order_by("name")[:300])
    mon_by_id = _monitoring_rows_by_server_id(ctx.user)
    endpoint_counts: dict[str, int] = {}
    for s in qs:
        key = f"{(s.host or '').strip().lower()}:{int(s.port or 22)}"
        endpoint_counts[key] = endpoint_counts.get(key, 0) + 1

    q_norm = normalize_host_hint(q).lower()
    q_low = q.lower()
    exact = [s for s in qs if (s.name or "").lower() == q_low or (s.name or "").lower() == q_norm or str(s.id) == q_low]
    partial = [s for s in qs if s not in exact and server_matches_query(s, q)]
    matches = exact or partial
    rows = [_server_row(s, mon_by_id, endpoint_counts) for s in matches[:15]]

    if not rows:
        # Help the model: top names, no UI card
        sample = [{"id": s.id, "name": s.name} for s in qs[:30]]
        return {
            "ok": False,
            "found": False,
            "query": q,
            "match": None,
            "matches": [],
            "sample_names": sample,
            "ui_table": False,
            "error": f"No server matching {q!r}",
            "target_url": "/servers",
        }

    best = rows[0]
    return {
        "ok": True,
        "found": True,
        "query": q,
        "match": best,
        "server_id": best["id"],
        "server_name": best["name"],
        "matches": rows,
        "match_count": len(rows),
        "exact": bool(exact),
        "ui_table": False,
        "target_url": best.get("terminal_url") or f"/servers/{best['id']}/terminal",
    }


def server_info(ctx: AssistantActionContext) -> dict[str, Any]:
    # Accept name when id omitted
    server_id = None
    try:
        server_id = _int_arg(ctx, "server_id", required=False)
    except Exception:  # noqa: BLE001
        server_id = None
    if server_id is None:
        name = str(ctx.input_payload.get("name") or ctx.input_payload.get("q") or "").strip()
        if name:
            resolved = resolve_server(
                AssistantActionContext(
                    user=ctx.user,
                    input_payload={"q": name},
                    request=ctx.request,
                    source=ctx.source,
                )
            )
            if not resolved.get("found"):
                raise AssistantActionError(resolved.get("error") or f"Server {name!r} not found", status=404)
            server_id = int(resolved["server_id"])
        else:
            raise AssistantActionError("server_id or name is required")
    assert server_id is not None
    s = _server_for_user(ctx.user, server_id)
    return {
        "id": s.id,
        "name": s.name,
        "host": s.host,
        "port": s.port,
        "username": getattr(s, "username", "") or "",
        "os_family": getattr(s, "os_family", "") or "",
        "ai_read_only": bool(getattr(s, "ai_read_only", False)),
        "ui_table": False,
        "target_url": f"/servers/{s.id}",
    }


def fleet_status(ctx: AssistantActionContext) -> dict[str, Any]:
    if not feature_allowed_for_user(ctx.user, "servers"):
        raise AssistantActionError("Feature access required: servers", status=403)

    servers = list(_accessible_servers_queryset(ctx.user).order_by("name")[:200])
    mon_by_id = _monitoring_rows_by_server_id(ctx.user)

    status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0}
    worst: list[dict[str, Any]] = []
    endpoints: set[str] = set()
    stale = 0
    for s in servers:
        mon = mon_by_id.get(int(s.id), {})
        status = str(mon.get("status") or "unknown")
        if status not in status_counts:
            status = "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        if mon.get("is_stale"):
            stale += 1
        endpoints.add(f"{(s.host or '').strip().lower()}:{int(s.port or 22)}")
        entry = {
            "server_id": s.id,
            "name": s.name,
            "status": status,
            "is_stale": bool(mon.get("is_stale")),
            "cpu_percent": mon.get("cpu_percent"),
            "mem_percent": mon.get("memory_percent"),
            "disk_percent": mon.get("disk_percent"),
        }
        if status in {"critical", "warning", "unreachable"}:
            worst.append(entry)
    worst = worst[:15]
    note = None
    if len(endpoints) == 1 and len(servers) > 1:
        only = next(iter(endpoints))
        note = f"{len(servers)} inventory names share one endpoint ({only}). Mirrored health is expected."
    return {
        "count": len(servers),
        "unique_endpoints": len(endpoints),
        "status_counts": status_counts,
        "stale_count": stale,
        "worst": worst,
        "note": note,
        "monitoring_hint": (
            "Background health is written by `run_monitor` (or fleet refresh), independent of open browser tabs. "
            "Live ~2s metrics stream only while a client is subscribed to /ws/monitoring/live/."
        ),
        "target_url": "/monitoring",
    }
