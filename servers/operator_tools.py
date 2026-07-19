"""Operator-chat read tools over inventory, insights, forecasts, alerts."""

from __future__ import annotations

import re
from typing import Any

from django.utils import timezone

from app.assistant_actions import (
    AssistantActionContext,
    AssistantActionError,
    AssistantActionSpec,
    register_action,
)
from core_ui.access import feature_allowed_for_user
from servers.views.server_helpers import _accessible_servers_queryset


# User asked to *see* inventory in chat (interactive card).
# Includes typos like «Списко» via спис\w*
_INVENTORY_CARD_RE = re.compile(
    r"(?:"
    r"спис\w*\s+сервер|"  # список/списко/списки серверов
    r"сервер\w*.{0,24}спис\w*|"
    r"(?:покажи|выведи|вывести|дай|дай-ка)\s+(?:мне\s+)?(?:спис\w*\s+)?сервер|"
    r"какие\s+сервер|"
    r"все\s+сервер|"
    r"list\s+(?:all\s+)?servers?|"
    r"show\s+(?:me\s+)?(?:the\s+)?(?:server\s+)?list|"
    r"show\s+(?:me\s+)?(?:all\s+)?servers?|"
    r"inventory\b|"
    r"инвентар|"
    r"^серверы\s*[.!?…]?\s*$|"
    r"серверы\s*\?"
    r")",
    re.I | re.M,
)

# Connect / metrics / diagnose — must NOT open fleet inventory card.
_HOST_ACTION_RE = re.compile(
    r"(?:"
    r"подключ|"
    r"connect|"
    r"ssh\b|"
    r"метрик|"
    r"metrics?|"
    r"диагност|"
    r"diagnos|"
    r"\bdf\b|"
    r"docker|"
    r"uptime|"
    r"проверь|"
    r"check\b|"
    r"соберите?|"
    r"collect|"
    r"run\s+command|"
    r"выполни"
    r")",
    re.I,
)

_HOST_HINT_RE = re.compile(
    r"(?:"
    r"@([\w.-]{2,64})"
    r"|(?:сервер(?:у|а|е|ом)?|server|host)\s+([^\s,;:]+)"
    r"|(?:подключись|подключить|connect(?:\s+to)?)\s+(?:к\s+|to\s+)?(?:сервер(?:у)?\s+)?([^\s,;:]+)"
    r"|(?:метрик\w*|metrics?|прогноз\w*|forecasts?)\s+(?:сервер\w*\s+)?([^\s,;:]+)"
    r"|(?:на|к)\s+(?:сервер(?:е|у)?\s+)?([a-zA-Z0-9_.-]{2,64})"
    r")",
    re.I,
)

# Spoken / Cyrillic nicknames → inventory name stems
_HOST_ALIASES: dict[str, str] = {
    "графана": "grafana",
    "графаны": "grafana",
    "графану": "grafana",
    "графаной": "grafana",
    "grafana": "grafana",
    "луникс": "lunix",
    "lunix": "lunix",
    "прометей": "prom",
    "prometheus": "prom",
    "пром": "prom",
    "prom": "prom",
    "редис": "redis",
    "redis": "redis",
    "бастион": "bastion",
    "bastion": "bastion",
}


def user_wants_inventory_card(user_message: str | None) -> bool:
    """True only when the operator asked to list inventory in the chat UI."""
    text = str(user_message or "").strip()
    if not text:
        return False
    # Named-host actions never get a fleet card (even if the word «сервер» appears).
    if _HOST_ACTION_RE.search(text) and not _INVENTORY_CARD_RE.search(text):
        return False
    if _INVENTORY_CARD_RE.search(text):
        return True
    # Short phrases: «серверы», «servers please»
    compact = re.sub(r"\s+", " ", text.lower()).strip()
    if len(compact) <= 56 and re.search(r"сервер|servers?", compact):
        if re.search(r"спис|list|show|покаж|какие|все|инвентар|inventory", compact):
            return True
        if compact in {"серверы", "servers", "сервера", "server list"}:
            return True
    return False


def user_wants_named_host_action(user_message: str | None) -> bool:
    """Connect / metrics / diagnose on a host — never fleet list card."""
    text = str(user_message or "").strip()
    if not text:
        return False
    if user_wants_inventory_card(text):
        return False
    return bool(_HOST_ACTION_RE.search(text))


def normalize_host_hint(token: str | None) -> str:
    """Map «графаны» → grafana, trim junk."""
    raw = str(token or "").strip().strip("«»\"'.,);:")
    if not raw:
        return ""
    low = raw.lower()
    if low in _HOST_ALIASES:
        return _HOST_ALIASES[low]
    # Stem common Russian endings
    for suf in ("ами", "ов", "ам", "ах", "ы", "и", "у", "е", "а", "ой", "ей"):
        if len(low) > 4 and low.endswith(suf):
            stem = low[: -len(suf)]
            if stem in _HOST_ALIASES:
                return _HOST_ALIASES[stem]
            if stem + "а" in _HOST_ALIASES:
                return _HOST_ALIASES[stem + "а"]
    return raw


def extract_server_hint(user_message: str | None) -> str | None:
    """Best-effort host token from natural language (графана, lunix, @web-prod-01)."""
    text = str(user_message or "").strip()
    if not text:
        return None
    m = _HOST_HINT_RE.search(text)
    if m:
        for g in m.groups():
            if g:
                token = g.strip().strip("«»\"'.,)@")
                if token.startswith("@"):
                    token = token[1:]
                if token and token.lower() not in {"сервер", "server", "host", "к", "to", "the", "и"}:
                    return normalize_host_hint(token) or token
    # Fallback: known aliases mentioned as whole words
    low = text.lower()
    for alias, canon in _HOST_ALIASES.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", low):
            return canon
    return None


def prepare_list_servers_arguments(
    arguments: dict[str, Any] | None,
    *,
    user_message: str | None,
) -> dict[str, Any]:
    """UI policy for list_servers.

    - Explicit list request → show_in_chat, no filter (full inventory card).
    - Never auto-inject q from the user message into list_servers (that caused
      «графаны» to stick forever and empty name lists). Host lookup is resolve_server.
    """
    args = dict(arguments or {})
    if user_wants_inventory_card(user_message):
        args["show_in_chat"] = True
        for key in ("q", "name", "query"):
            args.pop(key, None)
        return args

    args["show_in_chat"] = False
    # Normalize model-supplied filter only — do not invent one from chat text.
    raw_q = str(args.get("q") or args.get("name") or args.get("query") or "").strip()
    if raw_q:
        args["q"] = normalize_host_hint(raw_q) or raw_q
        args.pop("name", None)
        args.pop("query", None)
    return args


def prefer_resolve_server_for_message(
    arguments: dict[str, Any] | None,
    *,
    user_message: str | None,
) -> dict[str, Any] | None:
    """If the user asked metrics/connect on a named host, return resolve_server args.

    Returns None when list_servers should still run (true inventory list).
    """
    if user_wants_inventory_card(user_message):
        return None
    if not user_wants_named_host_action(user_message):
        return None
    args = arguments if isinstance(arguments, dict) else {}
    model_q = str(args.get("q") or args.get("name") or args.get("query") or "").strip()
    hint = extract_server_hint(user_message)
    q = normalize_host_hint(model_q) or hint
    if not q:
        return None
    return {"q": q}


def server_matches_query(server, q: str) -> bool:
    """Loose name/host match: grafana ↔ grafana-01, графаны → grafana."""
    q_raw = (q or "").strip()
    if not q_raw:
        return True
    q_norm = normalize_host_hint(q_raw).lower()
    q_low = q_raw.lower()
    name = (getattr(server, "name", None) or "").lower()
    host = (getattr(server, "host", None) or "").lower()
    tags = str(getattr(server, "tags", "") or "").lower()
    if str(getattr(server, "id", "")) == q_low:
        return True
    for token in {q_low, q_norm}:
        if not token:
            continue
        if token in name or token in host or token in tags:
            return True
        if name.startswith(token) or token.startswith(name.split("-")[0] if name else ""):
            if name and (name.startswith(token) or token in name.replace("-", "")):
                return True
        # stem match: grafana vs grafana-01
        name_stem = name.split("-")[0] if name else ""
        if name_stem and (name_stem == token or token.startswith(name_stem) or name_stem.startswith(token)):
            if len(token) >= 3 and len(name_stem) >= 3:
                return True
    return False


def _int_arg(ctx: AssistantActionContext, key: str, *, required: bool = True) -> int | None:
    value = ctx.input_payload.get(key)
    if value is None or value == "":
        if required:
            raise AssistantActionError(f"{key} is required")
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise AssistantActionError(f"{key} must be positive")
    return parsed


def _server_for_user(user, server_id: int):
    server = _accessible_servers_queryset(user).filter(pk=server_id).first()
    if server is None:
        raise AssistantActionError("Server not found or not accessible", status=404)
    return server


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
        "tags": [
            part.strip()
            for part in str(getattr(s, "tags", "") or "").split(",")
            if part.strip()
        ],
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
    full_name_index = {
        str(s.name): int(s.id) for s in all_servers if getattr(s, "name", None)
    }

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
        {
            f"{(s.host or '').strip().lower()}:{int(s.port or 22)}"
            for s in (qs if emit_rows else all_servers)
        }
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
        model_notes.append(
            "UI card suppressed (lookup mode). "
            "For a named host prefer operator.resolve_server(q=…)."
        )
    if not emit_rows:
        model_notes.append(
            f"Compact inventory: {len(full_name_index)} name(s) in name_index only "
            f"(no server rows)."
        )
    if unique_endpoints and unique_endpoints < len(all_servers if not emit_rows else servers or all_servers):
        mirror = (
            f"{len(all_servers)} inventory rows map to {unique_endpoints} physical host:port endpoint(s)."
        )
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
            "UI card attached. Answer ≤1 sentence with counts only. Zero host-name bullets."
            if show_in_chat
            else None
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
    exact = [
        s
        for s in qs
        if (s.name or "").lower() == q_low
        or (s.name or "").lower() == q_norm
        or str(s.id) == q_low
    ]
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
        note = (
            f"{len(servers)} inventory names share one endpoint ({only}). "
            "Mirrored health is expected."
        )
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


def _forecast_metric_key(kind: str, target: str, evidence: dict) -> str | None:
    if evidence.get("metric_key"):
        return str(evidence["metric_key"])
    k = (kind or "").lower()
    t = (target or "").strip()
    if k == "disk_full":
        mount = evidence.get("mount") or (t.split(":", 1)[-1] if t.startswith("disk:") else t)
        return f"disk.{mount}.percent" if mount else None
    if k == "inode_full":
        mount = evidence.get("mount") or (t.split(":", 1)[-1] if t.startswith("inode:") else t)
        return f"disk.{mount}.inode_percent" if mount else None
    if k == "memory_pressure":
        return "mem.available_mb"
    if k == "swap_growth":
        return "swap.percent"
    if k == "log_error_surge":
        return "journal.err_10m"
    return None


def _forecast_spark_series(
    *,
    server_id: int | None,
    kind: str,
    target: str,
    evidence: dict,
    current_value: float | None,
    slope_per_day: float | None,
    threshold: float | None,
) -> list[float]:
    """Real metric history when available; otherwise a tiny synthetic trend."""
    points: list[float] = []
    metric_key = _forecast_metric_key(kind, target, evidence)
    if server_id and metric_key:
        try:
            from django.utils import timezone

            from servers.forecasting import fetch_series

            series = fetch_series(int(server_id), metric_key, now=timezone.now())
            points = [float(y) for _x, y in series[-28:]]
        except Exception:  # noqa: BLE001
            points = []
    if len(points) >= 2:
        return points
    # Synthetic mini-trend so the UI still shows a quiet sparkline.
    if current_value is None:
        return []
    try:
        cur = float(current_value)
    except (TypeError, ValueError):
        return []
    slope = float(slope_per_day or 0.0)
    # Walk 12 steps backward (~half day units) then end at current.
    n = 12
    synth = []
    for i in range(n):
        # i=0 oldest
        age = (n - 1 - i) * 0.5
        synth.append(round(cur - slope * age, 3))
    if threshold is not None:
        try:
            # Soft mark toward threshold at the end for visual context
            th = float(threshold)
            synth.append(round((cur * 2 + th) / 3, 3))
        except (TypeError, ValueError):
            pass
    return synth


def server_forecasts(ctx: AssistantActionContext) -> dict[str, Any]:
    server_id = _int_arg(ctx, "server_id", required=False)
    from servers.models import ServerPrediction

    qs = ServerPrediction.objects.filter(status=ServerPrediction.STATUS_ACTIVE).select_related("server")
    if server_id:
        _server_for_user(ctx.user, server_id)
        qs = qs.filter(server_id=server_id)
    else:
        accessible = _accessible_servers_queryset(ctx.user).values_list("id", flat=True)
        qs = qs.filter(server_id__in=accessible)
    rows = []
    # Fleet view: one row per physical endpoint (host:port) + kind + target
    seen_endpoint: set[tuple[str, str, str]] = set()
    skipped = 0
    for p in qs.order_by("eta_days", "id")[:120]:
        evidence = p.evidence if isinstance(p.evidence, dict) else {}
        host = (p.server.host or "").strip().lower() if p.server_id else ""
        port = int(getattr(p.server, "port", None) or 22) if p.server_id else 0
        endpoint = f"{host}:{port}" if host else f"id:{p.server_id}"
        kind = str(p.kind or "")
        target = str(getattr(p, "target", "") or "")
        if not server_id:
            key = (endpoint, kind, target)
            if key in seen_endpoint:
                skipped += 1
                continue
            seen_endpoint.add(key)
        series = _forecast_spark_series(
            server_id=p.server_id,
            kind=kind,
            target=target,
            evidence=evidence,
            current_value=p.current_value,
            slope_per_day=p.slope_per_day,
            threshold=p.threshold,
        )
        rows.append(
            {
                "id": p.id,
                "server_id": p.server_id,
                "server_name": p.server.name if p.server_id else "",
                "host": host,
                "kind": p.kind,
                "target": target,
                "severity": p.severity,
                "eta_days": p.eta_days,
                "current_value": p.current_value,
                "threshold": p.threshold,
                "unit": p.unit,
                "slope_per_day": p.slope_per_day,
                "confidence": p.confidence,
                "series": series,
                "message": str(evidence.get("summary") or evidence.get("message") or "")[:300],
            }
        )
        if len(rows) >= 50:
            break
    summary = "ok" if not rows else f"{len(rows)}"
    if skipped:
        summary = f"{len(rows)} unique endpoints · collapsed {skipped} mirrored clones"
    return {
        "predictions": rows,
        "count": len(rows),
        "skipped_mirrored_duplicates": skipped,
        "empty": len(rows) == 0,
        "summary": summary,
        "note": (
            "Predictions de-duplicated by host:port — many inventory names can point at one machine."
            if skipped
            else None
        ),
        "target_url": "/monitoring",
    }


def list_alerts(ctx: AssistantActionContext) -> dict[str, Any]:
    """List alerts. Prefer alert_id / server_id when investigating a specific incident.

    Without filters, returns recent *unresolved* alerts and de-duplicates rows that
    share the same physical host:port (mirrored inventory aliases).
    """
    from servers.models import ServerAlert

    accessible = list(_accessible_servers_queryset(ctx.user).values_list("id", flat=True))
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    alert_id = _int_arg(ctx, "alert_id", required=False)
    server_id = _int_arg(ctx, "server_id", required=False)
    unresolved_only = payload.get("unresolved_only")
    if unresolved_only is None:
        unresolved_only = True
    unresolved_only = bool(unresolved_only)
    try:
        limit = max(1, min(int(payload.get("limit") or 25), 60))
    except (TypeError, ValueError):
        limit = 25
    dedupe_hosts = payload.get("dedupe_hosts")
    if dedupe_hosts is None:
        # Only auto-dedupe fleet-wide dumps; keep full set when scoped to one server.
        dedupe_hosts = server_id is None and alert_id is None
    dedupe_hosts = bool(dedupe_hosts)

    qs = ServerAlert.objects.filter(server_id__in=accessible).select_related("server").order_by("-created_at")
    if alert_id:
        qs = qs.filter(pk=alert_id)
    if server_id:
        _server_for_user(ctx.user, server_id)
        qs = qs.filter(server_id=server_id)
    if unresolved_only:
        qs = qs.filter(is_resolved=False)

    rows = list(qs[: max(limit * 4, 40)])
    alerts: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    skipped_mirrors = 0
    for a in rows:
        host = (getattr(a.server, "host", None) or "").strip().lower() if a.server_id else ""
        port = int(getattr(a.server, "port", None) or 22) if a.server_id else 0
        endpoint = f"{host}:{port}" if host else f"server:{a.server_id}"
        fingerprint = ""
        meta = a.metadata if isinstance(getattr(a, "metadata", None), dict) else {}
        if isinstance(meta, dict):
            fingerprint = str(meta.get("fingerprint") or "")[:120]
        dedupe_key = (endpoint, str(a.alert_type or ""), fingerprint or str(a.title or "")[:120])
        if dedupe_hosts and dedupe_key in seen_keys:
            skipped_mirrors += 1
            continue
        seen_keys.add(dedupe_key)
        alerts.append(
            {
                "id": a.id,
                "server_id": a.server_id,
                "server_name": a.server.name if a.server_id else "",
                "host": host,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "title": a.title,
                "message": (a.message or "")[:300],
                "is_resolved": bool(a.is_resolved),
                "metadata": {
                    k: meta.get(k)
                    for k in ("fingerprint", "eta_days", "mount", "current_value", "threshold")
                    if isinstance(meta, dict) and k in meta
                }
                if isinstance(meta, dict)
                else {},
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
        )
        if len(alerts) >= limit:
            break

    # Focused single-alert investigation package
    focus = None
    if alert_id and alerts:
        focus = get_alert_detail(ctx.user, alert_id)

    return {
        "alerts": alerts,
        "count": len(alerts),
        "skipped_mirrored_duplicates": skipped_mirrors,
        "filters": {
            "alert_id": alert_id,
            "server_id": server_id,
            "unresolved_only": unresolved_only,
            "dedupe_hosts": dedupe_hosts,
        },
        "focus": focus,
        "note": (
            "Inventory rows that share host:port mirror one physical endpoint — "
            "identical forecast alerts are collapsed unless server_id/alert_id is set."
            if skipped_mirrors
            else None
        ),
        "target_url": f"/monitoring" if not alert_id else f"/monitoring?alert={alert_id}",
    }


def get_alert_detail(user, alert_id: int) -> dict[str, Any] | None:
    """Rich package for «разбери алерт #N»: alert + mounts + prediction + mirror siblings."""
    from servers.models import ServerAlert, ServerHealthCheck, ServerMetricSample, ServerPrediction

    accessible = _accessible_servers_queryset(user)
    alert = (
        ServerAlert.objects.filter(pk=alert_id, server_id__in=accessible.values_list("id", flat=True))
        .select_related("server")
        .first()
    )
    if alert is None:
        return None
    server = alert.server
    host = (server.host or "").strip() if server else ""
    port = int(getattr(server, "port", None) or 22) if server else 22
    siblings = []
    if server and host:
        for s in accessible.filter(host__iexact=host, port=port).exclude(pk=server.id).order_by("name")[:20]:
            siblings.append({"id": s.id, "name": s.name})

    health = ServerHealthCheck.objects.filter(server_id=server.id).order_by("-checked_at").first() if server else None
    sample = ServerMetricSample.objects.filter(server_id=server.id).order_by("-collected_at").first() if server else None
    mounts = []
    if sample and isinstance(sample.disk_mounts, list):
        for m in sample.disk_mounts[:12]:
            if not isinstance(m, dict):
                continue
            mounts.append(
                {
                    "mount": m.get("mount"),
                    "percent": m.get("percent"),
                    "used_gb": m.get("used_gb"),
                    "total_gb": m.get("total_gb"),
                }
            )
    mirrored_from = None
    if sample and isinstance(sample.extra, dict):
        mirrored_from = sample.extra.get("mirrored_from_server_id")

    meta = alert.metadata if isinstance(alert.metadata, dict) else {}
    fingerprint = str(meta.get("fingerprint") or "")
    prediction = None
    if server:
        pred_qs = ServerPrediction.objects.filter(server_id=server.id, status=ServerPrediction.STATUS_ACTIVE)
        # Match forecast fingerprint like forecast:disk_full:disk:/mnt/d
        if "disk_full" in fingerprint or "disk:" in fingerprint:
            mount = None
            if "disk:" in fingerprint:
                mount = fingerprint.split("disk:", 1)[-1].strip()
            if mount:
                prediction = pred_qs.filter(kind="disk_full", target=f"disk:{mount}").first()
            if prediction is None:
                prediction = pred_qs.filter(kind="disk_full").first()
        if prediction is None:
            prediction = pred_qs.order_by("eta_days", "id").first()

    pred_payload = None
    if prediction is not None:
        pred_payload = {
            "id": prediction.id,
            "kind": prediction.kind,
            "target": prediction.target,
            "severity": prediction.severity,
            "eta_days": prediction.eta_days,
            "current_value": prediction.current_value,
            "threshold": prediction.threshold,
            "unit": prediction.unit,
            "slope_per_day": prediction.slope_per_day,
            "confidence": prediction.confidence,
        }

    root_disk = getattr(health, "disk_percent", None)
    return {
        "alert": {
            "id": alert.id,
            "title": alert.title,
            "message": (alert.message or "")[:500],
            "severity": alert.severity,
            "alert_type": alert.alert_type,
            "is_resolved": bool(alert.is_resolved),
            "metadata": meta,
        },
        "server": {
            "id": server.id if server else None,
            "name": server.name if server else "",
            "host": host,
            "port": port,
        },
        "metrics": {
            "disk_percent_root": root_disk,
            "disk_percent_note": (
                "disk_percent is ROOT mount (/) only — check disk_mounts for /mnt/* volumes"
            ),
            "cpu_percent": getattr(sample, "cpu_percent", None) or getattr(health, "cpu_percent", None),
            "mem_percent": getattr(sample, "memory_percent", None) or getattr(health, "memory_percent", None),
            "disk_mounts": mounts,
            "mirrored_from_server_id": mirrored_from,
        },
        "prediction": pred_payload,
        "sibling_inventory_same_host": siblings,
        "sibling_count": len(siblings),
        "interpretation": _interpret_alert(alert, root_disk=root_disk, mounts=mounts, siblings=siblings, mirrored_from=mirrored_from),
    }


def _interpret_alert(
    alert,
    *,
    root_disk: float | None,
    mounts: list[dict[str, Any]],
    siblings: list[dict[str, Any]],
    mirrored_from: Any,
) -> str:
    parts: list[str] = []
    title = str(alert.title or "")
    if "/mnt/" in title or "диск" in title.lower() or "disk" in title.lower():
        parts.append(
            "Прогноз по конкретному mount (не по корневому disk_percent). "
            f"disk_percent корня сейчас {root_disk}% — это / , не /mnt/*."
        )
        hot = [m for m in mounts if isinstance(m.get("percent"), (int, float)) and float(m["percent"]) >= 80]
        if hot:
            parts.append(
                "Горячие mount: "
                + ", ".join(f"{m.get('mount')}={m.get('percent')}%" for m in hot[:5])
            )
    if siblings:
        parts.append(
            f"Ещё {len(siblings)} inventory-алиасов на том же host:port "
            f"({', '.join(s['name'] for s in siblings[:5])}{'…' if len(siblings) > 5 else ''}) — "
            "метрики зеркалятся с одного физического хоста, поэтому одинаковые прогнозы — не 16 разных машин."
        )
    if mirrored_from:
        parts.append(f"Сэмпл mirrored_from_server_id={mirrored_from}.")
    return " ".join(parts) if parts else "См. title/message алерта и prediction."


def list_certificates(ctx: AssistantActionContext) -> dict[str, Any]:
    from servers.models import ServerCertificate

    accessible = _accessible_servers_queryset(ctx.user).values_list("id", flat=True)
    now = timezone.now()
    qs = ServerCertificate.objects.filter(server_id__in=accessible).select_related("server").order_by("not_after")[:50]
    certs = []
    for c in qs:
        days_left = None
        if c.not_after:
            days_left = round((c.not_after - now).total_seconds() / 86400, 1)
        certs.append(
            {
                "id": c.id,
                "server_id": c.server_id,
                "server_name": c.server.name if c.server_id else "",
                "subject": (c.subject or "")[:200],
                "port": c.port,
                "not_after": c.not_after.isoformat() if c.not_after else None,
                "days_left": days_left,
            }
        )
    return {"certificates": certs, "count": len(certs), "target_url": "/monitoring"}


def fleet_ai_insights(ctx: AssistantActionContext) -> dict[str, Any]:
    try:
        from servers.ai_insights import latest_fleet_insight
        from servers.models import ServerAiInsight
    except Exception as exc:  # noqa: BLE001
        return {"insights": [], "count": 0, "note": f"AI insights unavailable: {exc}"}

    fleet = None
    try:
        fleet = latest_fleet_insight()
    except Exception:  # noqa: BLE001
        fleet = None
    rows = []
    if fleet is not None:
        rows.append(
            {
                "id": fleet.id,
                "scope": "fleet",
                "verdict": getattr(fleet, "verdict", "") or "",
                "content": (getattr(fleet, "content", None) or "")[:500],
                "created_at": fleet.created_at.isoformat() if getattr(fleet, "created_at", None) else None,
            }
        )
    try:
        accessible = list(_accessible_servers_queryset(ctx.user).values_list("id", flat=True)[:50])
        for row in ServerAiInsight.objects.filter(server_id__in=accessible).order_by("-created_at")[:15]:
            rows.append(
                {
                    "id": row.id,
                    "scope": "server",
                    "server_id": row.server_id,
                    "verdict": getattr(row, "verdict", "") or "",
                    "content": (getattr(row, "content", None) or "")[:400],
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
    except Exception:  # noqa: BLE001
        pass
    return {"insights": rows, "count": len(rows), "target_url": "/monitoring"}


def server_metrics(ctx: AssistantActionContext) -> dict[str, Any]:
    server_id = _int_arg(ctx, "server_id")
    assert server_id is not None
    server = _server_for_user(ctx.user, server_id)
    from servers.models import ServerHealthCheck, ServerMetricSample

    health = ServerHealthCheck.objects.filter(server_id=server_id).order_by("-checked_at").first()
    sample = ServerMetricSample.objects.filter(server_id=server_id).order_by("-collected_at").first()
    mounts: list[dict[str, Any]] = []
    if sample and isinstance(sample.disk_mounts, list):
        for m in sample.disk_mounts[:12]:
            if isinstance(m, dict):
                mounts.append(
                    {
                        "mount": m.get("mount"),
                        "percent": m.get("percent"),
                        "used_gb": m.get("used_gb"),
                        "total_gb": m.get("total_gb"),
                    }
                )
    mirrored_from = None
    if sample and isinstance(sample.extra, dict):
        mirrored_from = sample.extra.get("mirrored_from_server_id")
    root_disk = getattr(health, "disk_percent", None)
    status = getattr(health, "status", None) or "unknown"
    has_samples = sample is not None or health is not None
    # Long English note is for the model only; UI uses short ui_note.
    status_note = None
    ui_note = None
    if status == "unreachable" and has_samples:
        status_note = (
            "Status «unreachable» is SSH/probe health — metrics below are the last successful sample, "
            "not proof that no data exists. Do not open a terminal just to read these numbers. "
            "Do not call list_servers; you already have server_id."
        )
        ui_note = "Последний снимок · SSH/probe unreachable"
    return {
        "server_id": server.id,
        "name": server.name,
        "host": server.host,
        "status": status,
        "cpu_percent": getattr(sample, "cpu_percent", None) if sample else getattr(health, "cpu_percent", None),
        "mem_percent": (
            getattr(sample, "memory_percent", None) if sample else getattr(health, "memory_percent", None)
        ),
        # Root filesystem only (/). Do NOT compare this to mount-specific forecasts.
        "disk_percent": root_disk,
        "disk_percent_is_root": True,
        "disk_mounts": mounts,
        "mirrored_from_server_id": mirrored_from,
        "collected_at": (
            sample.collected_at.isoformat()
            if sample and getattr(sample, "collected_at", None)
            else (health.checked_at.isoformat() if health else None)
        ),
        "status_note": status_note,
        "ui_note": ui_note,
        "ui_metrics": True,
        "target_url": f"/servers/{server.id}",
    }


def server_memory(ctx: AssistantActionContext) -> dict[str, Any]:
    server_id = _int_arg(ctx, "server_id")
    assert server_id is not None
    _server_for_user(ctx.user, server_id)
    from core_ui.services.operator_memory import memory_hints_for_server
    from servers.services.memory_service import get_memory_overview

    hints = memory_hints_for_server(server_id, limit=8)
    try:
        overview = get_memory_overview(server_id)
        stats = overview.get("stats") or {}
    except Exception:  # noqa: BLE001
        stats = {}
    return {
        "server_id": server_id,
        "hints": hints,
        "stats": stats,
        "target_url": f"/servers/{server_id}",
    }


def save_memory_lesson(ctx: AssistantActionContext) -> dict[str, Any]:
    """Save a solved-problem lesson into server memory cards."""
    from core_ui.services.operator_memory import save_lesson_from_operator, server_ids_from_arguments

    title = str(ctx.input_payload.get("title") or "").strip()
    lesson = str(ctx.input_payload.get("lesson") or ctx.input_payload.get("summary") or "").strip()
    server_ids = server_ids_from_arguments(ctx.input_payload)
    chat_id = ctx.input_payload.get("chat_id")
    try:
        chat_id_int = int(chat_id) if chat_id not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("chat_id must be an integer") from exc
    run_dream = bool(ctx.input_payload.get("run_dream", False))
    try:
        return save_lesson_from_operator(
            user=ctx.user,
            title=title,
            lesson=lesson,
            server_ids=server_ids,
            chat_id=chat_id_int,
            run_dream=run_dream,
        )
    except PermissionError as exc:
        raise AssistantActionError(str(exc), status=403) from exc
    except ValueError as exc:
        raise AssistantActionError(str(exc)) from exc


def promote_chat_memory(ctx: AssistantActionContext) -> dict[str, Any]:
    """Promote an important Operator conversation into durable memory (+ optional dream)."""
    from core_ui.services.operator_memory import promote_chat_to_memory, server_ids_from_arguments

    chat_id = ctx.input_payload.get("chat_id")
    try:
        chat_id_int = int(chat_id)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("chat_id is required") from exc
    title = str(ctx.input_payload.get("title") or "").strip()
    lesson = str(ctx.input_payload.get("lesson") or ctx.input_payload.get("summary") or "").strip()
    server_ids = server_ids_from_arguments(ctx.input_payload) or None
    run_dream = bool(ctx.input_payload.get("run_dream", True))
    try:
        return promote_chat_to_memory(
            user=ctx.user,
            chat_id=chat_id_int,
            title=title,
            lesson=lesson,
            server_ids=server_ids,
            run_dream=run_dream,
        )
    except LookupError as exc:
        raise AssistantActionError(str(exc), status=404) from exc
    except PermissionError as exc:
        raise AssistantActionError(str(exc), status=403) from exc
    except ValueError as exc:
        raise AssistantActionError(str(exc)) from exc


def metric_series(ctx: AssistantActionContext) -> dict[str, Any]:
    """Return a numeric series for inline charts (from rollups or health samples)."""
    server_id = _int_arg(ctx, "server_id")
    assert server_id is not None
    server = _server_for_user(ctx.user, server_id)
    metric_key = str(ctx.input_payload.get("metric_key") or "cpu_percent").strip()
    points: list[float] = []
    try:
        from servers.models import ServerMetricRollup

        rows = (
            ServerMetricRollup.objects.filter(
                server_id=server_id,
                metric_key=metric_key,
                granularity=ServerMetricRollup.GRANULARITY_HOUR,
            )
            .order_by("-bucket_start")[:48]
        )
        points = [float(r.value_avg) for r in reversed(list(rows)) if r.value_avg is not None]
    except Exception:  # noqa: BLE001
        points = []
    if len(points) < 2:
        from servers.models import ServerHealthCheck

        samples = ServerHealthCheck.objects.filter(server_id=server_id).order_by("-checked_at")[:48]
        field = {
            "cpu_percent": "cpu_percent",
            "memory_percent": "memory_percent",
            "mem_percent": "memory_percent",
            "disk_percent": "disk_percent",
        }.get(metric_key, "cpu_percent")
        vals = []
        for s in reversed(list(samples)):
            v = getattr(s, field, None)
            if v is not None:
                vals.append(float(v))
        points = vals
    return {
        "server_id": server.id,
        "server_name": server.name,
        "metric_key": metric_key,
        "title": f"{server.name} · {metric_key}",
        "series": points,
        "unit": "%",
        "count": len(points),
        "target_url": f"/servers/{server.id}",
    }


def propose_plan(ctx: AssistantActionContext) -> dict[str, Any]:
    """Approve a multi-step plan (executed as a single confirm gate)."""
    title = str(ctx.input_payload.get("title") or "Plan").strip()[:200]
    steps = ctx.input_payload.get("steps") if isinstance(ctx.input_payload.get("steps"), list) else []
    if not steps:
        raise AssistantActionError("steps is required")
    normalized = []
    for i, step in enumerate(steps[:20]):
        if isinstance(step, dict):
            normalized.append(
                {
                    "id": i + 1,
                    "text": str(step.get("text") or step.get("description") or "")[:400],
                    "tool": str(step.get("tool") or "")[:80],
                }
            )
        else:
            normalized.append({"id": i + 1, "text": str(step)[:400], "tool": ""})
    return {
        "ok": True,
        "approved": True,
        "title": title,
        "steps": normalized,
        "message": "Plan approved by operator. Execute steps in order using tools.",
    }


def register_operator_tools() -> None:
    specs = [
        AssistantActionSpec(
            action_type="operator.resolve_server",
            label="Resolve server",
            description=(
                "Resolve one inventory host by name/host/id (e.g. lunix). "
                "Use for connect / SSH / diagnostics on a named host. "
                "Does NOT show the fleet inventory card in chat."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "Server name, host, or id (e.g. lunix)",
                    },
                    "name": {"type": "string", "description": "Alias for q"},
                },
            },
            handler=resolve_server,
        ),
        AssistantActionSpec(
            action_type="operator.list_servers",
            label="List servers",
            description=(
                "Inventory. For a named host ALWAYS use operator.resolve_server instead. "
                "Full list card appears only when the user asked to list servers "
                "(platform sets show_in_chat). Do not use this to «find» grafana/lunix."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "Filter by name/host/tag/id (e.g. grafana) — no fleet card",
                    },
                    "name": {"type": "string", "description": "Alias for q"},
                    "show_in_chat": {
                        "type": "boolean",
                        "description": "Platform-controlled; true only for explicit list-inventory requests.",
                    },
                },
            },
            handler=list_servers,
        ),
        AssistantActionSpec(
            action_type="operator.server_info",
            label="Server info",
            description="Get details for one accessible server (OS, host, ai_read_only). Accepts server_id or name.",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer"},
                    "name": {"type": "string", "description": "Server name if id unknown"},
                },
            },
            handler=server_info,
        ),
        AssistantActionSpec(
            action_type="operator.fleet_status",
            label="Fleet status",
            description="Fleet health summary: status counts and worst servers.",
            required_feature="servers",
            risk="read",
            handler=fleet_status,
        ),
        AssistantActionSpec(
            action_type="operator.server_metrics",
            label="Server metrics",
            description=(
                "Latest CPU/memory/disk for one server. disk_percent is ROOT (/) only; "
                "see disk_mounts for /mnt/* . Mirrored inventory may set mirrored_from_server_id."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer"}},
                "required": ["server_id"],
            },
            handler=server_metrics,
        ),
        AssistantActionSpec(
            action_type="operator.server_forecasts",
            label="Server forecasts",
            description=(
                "Active capacity/cert forecasts. Pass server_id for one host. "
                "Fleet mode collapses duplicate predictions from mirrored host:port inventory."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer", "description": "Optional server filter"}},
            },
            handler=server_forecasts,
        ),
        AssistantActionSpec(
            action_type="operator.list_alerts",
            label="List alerts",
            description=(
                "Monitoring alerts. For «разбери алерт #N» ALWAYS pass alert_id=N "
                "(returns focus package with mounts/prediction). Optional server_id. "
                "Fleet dumps collapse mirrored host:port clones."
            ),
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "alert_id": {"type": "integer", "description": "Investigate one alert by id"},
                    "server_id": {"type": "integer", "description": "Filter to one server"},
                    "unresolved_only": {"type": "boolean", "description": "Default true"},
                    "limit": {"type": "integer", "description": "Max rows (default 25)"},
                    "dedupe_hosts": {"type": "boolean", "description": "Collapse same host:port clones"},
                },
            },
            handler=list_alerts,
        ),
        AssistantActionSpec(
            action_type="operator.list_certificates",
            label="List certificates",
            description="TLS certificates with days left until expiry.",
            required_feature="servers",
            risk="read",
            handler=list_certificates,
        ),
        AssistantActionSpec(
            action_type="operator.fleet_ai_insights",
            label="Fleet AI insights",
            description="Latest AI analyst verdicts for fleet and servers.",
            required_feature="servers",
            risk="read",
            handler=fleet_ai_insights,
        ),
        AssistantActionSpec(
            action_type="operator.server_memory",
            label="Server memory",
            description="Operational memory card: incidents, habits, risks for one server.",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer"}},
                "required": ["server_id"],
            },
            handler=server_memory,
        ),
        AssistantActionSpec(
            action_type="operator.memory.save_lesson",
            label="Save lesson to memory",
            description=(
                "Persist a short solved-problem lesson into server memory cards. "
                "Use after a successful diagnosis/fix. Requires title, lesson, server_ids."
            ),
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "lesson": {"type": "string", "description": "What was wrong and how it was fixed"},
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "server_id": {"type": "integer"},
                    "run_dream": {"type": "boolean", "description": "Run nearline dream compaction after save"},
                    "chat_id": {"type": "integer"},
                },
                "required": ["title", "lesson"],
            },
            handler=save_memory_lesson,
        ),
        AssistantActionSpec(
            action_type="operator.memory.promote_chat",
            label="Promote chat to memory",
            description=(
                "When a conversation solved something important: distill it into durable "
                "server memory and optionally run a dream cycle. Prefer an explicit lesson summary."
            ),
            required_feature="servers",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "chat_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "lesson": {"type": "string", "description": "Best: explicit root-cause + fix summary"},
                    "server_ids": {"type": "array", "items": {"type": "integer"}},
                    "run_dream": {"type": "boolean", "description": "Default true — compact into patterns"},
                },
            },
            handler=promote_chat_memory,
        ),
        AssistantActionSpec(
            action_type="operator.metric_series",
            label="Metric series",
            description="Time series for a metric (cpu_percent, memory_percent, disk_percent) for charts.",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "integer"},
                    "metric_key": {"type": "string", "description": "cpu_percent|memory_percent|disk_percent"},
                },
                "required": ["server_id"],
            },
            handler=metric_series,
        ),
        AssistantActionSpec(
            action_type="operator.propose_plan",
            label="Propose plan",
            description=(
                "Propose a multi-step plan checklist for complex tasks (>2 mutations). "
                "Operator approves once; then execute steps with tools."
            ),
            required_feature="orchestrator",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "tool": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["title", "steps"],
            },
            handler=propose_plan,
        ),
    ]
    for spec in specs:
        try:
            register_action(spec)
        except ValueError:
            # Already registered (e.g. double ready())
            pass
