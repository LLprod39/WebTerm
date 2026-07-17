"""Operator-chat read tools over inventory, insights, forecasts, alerts."""

from __future__ import annotations

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


def list_servers(ctx: AssistantActionContext) -> dict[str, Any]:
    qs = _accessible_servers_queryset(ctx.user).order_by("name")[:100]
    # Best-effort latest health status for interactive chips
    status_by_id: dict[int, str] = {}
    try:
        from servers.models import ServerHealthCheck

        ids = [s.id for s in qs]
        for h in ServerHealthCheck.objects.filter(server_id__in=ids).order_by("server_id", "-checked_at"):
            if h.server_id not in status_by_id:
                status_by_id[h.server_id] = h.status or "unknown"
    except Exception:  # noqa: BLE001
        status_by_id = {}

    # Count inventory aliases per physical endpoint (host:port)
    endpoint_counts: dict[str, int] = {}
    for s in qs:
        key = f"{(s.host or '').strip().lower()}:{int(s.port or 22)}"
        endpoint_counts[key] = endpoint_counts.get(key, 0) + 1

    servers = []
    for s in qs:
        key = f"{(s.host or '').strip().lower()}:{int(s.port or 22)}"
        servers.append(
            {
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
                "status": status_by_id.get(s.id, "unknown"),
                "shared_endpoint_count": endpoint_counts.get(key, 1),
                "terminal_url": f"/servers/{s.id}/terminal",
            }
        )
    unique_endpoints = sum(1 for n in endpoint_counts.values() if n)
    # Actually unique = len(endpoint_counts)
    unique_endpoints = len(endpoint_counts)
    note = None
    if unique_endpoints and unique_endpoints < len(servers):
        note = (
            f"{len(servers)} inventory rows map to {unique_endpoints} physical host:port "
            "endpoint(s); health/metrics are mirrored across aliases."
        )
    return {
        "servers": servers,
        "count": len(servers),
        "unique_endpoints": unique_endpoints,
        "note": note,
        "target_url": "/servers",
    }


def server_info(ctx: AssistantActionContext) -> dict[str, Any]:
    server_id = _int_arg(ctx, "server_id")
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
        "target_url": f"/servers/{s.id}",
    }


def fleet_status(ctx: AssistantActionContext) -> dict[str, Any]:
    if not feature_allowed_for_user(ctx.user, "servers"):
        raise AssistantActionError("Feature access required: servers", status=403)
    from servers.models import ServerHealthCheck

    servers = list(_accessible_servers_queryset(ctx.user).order_by("name")[:200])
    ids = [s.id for s in servers]
    latest_health: dict[int, Any] = {}
    for h in ServerHealthCheck.objects.filter(server_id__in=ids).order_by("server_id", "-checked_at"):
        if h.server_id not in latest_health:
            latest_health[h.server_id] = h

    status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0}
    worst: list[dict[str, Any]] = []
    for s in servers:
        health = latest_health.get(s.id)
        status = getattr(health, "status", None) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        entry = {
            "server_id": s.id,
            "name": s.name,
            "status": status,
            "cpu_percent": getattr(health, "cpu_percent", None),
            "mem_percent": getattr(health, "memory_percent", None),
            "disk_percent": getattr(health, "disk_percent", None),
        }
        if status in {"critical", "warning", "unreachable"}:
            worst.append(entry)
    worst = worst[:15]
    return {
        "count": len(servers),
        "status_counts": status_counts,
        "worst": worst,
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
    return {
        "server_id": server.id,
        "name": server.name,
        "host": server.host,
        "status": getattr(health, "status", None) or "unknown",
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
            action_type="operator.list_servers",
            label="List servers",
            description="List inventory servers accessible to the operator.",
            required_feature="servers",
            risk="read",
            handler=list_servers,
        ),
        AssistantActionSpec(
            action_type="operator.server_info",
            label="Server info",
            description="Get details for one accessible server (OS, host, ai_read_only).",
            required_feature="servers",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {"server_id": {"type": "integer"}},
                "required": ["server_id"],
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
