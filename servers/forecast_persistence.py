"""Persist deterministic forecasts and turn them into stable alerts.

build_server_predictions (servers.forecasting) is stateless; this module
gives each (server, kind, target) forecast a stable row that re-activates on
recurrence and resolves when the trend disappears, and mirrors the
critical/warning ones into ServerAlert with update-in-place semantics so a
persisting forecast never spams duplicate alerts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from loguru import logger

from servers.forecasting import build_server_predictions
from servers.models import Server, ServerAlert, ServerPrediction

_ALERTABLE_SEVERITIES = {"critical", "warning"}

_PREDICTION_FIELDS = (
    "severity",
    "eta_days",
    "predicted_for",
    "current_value",
    "threshold",
    "unit",
    "slope_per_day",
    "confidence",
    "evidence",
)


def _prediction_defaults(item: dict[str, Any], now: datetime) -> dict[str, Any]:
    defaults = {field: item.get(field) for field in _PREDICTION_FIELDS}
    defaults["confidence"] = item.get("confidence") or 0.5
    defaults["unit"] = item.get("unit") or ""
    defaults["evidence"] = item.get("evidence") or {}
    if item.get("predicted_for"):
        defaults["predicted_for"] = datetime.fromisoformat(item["predicted_for"])
    defaults["status"] = ServerPrediction.STATUS_ACTIVE
    defaults["last_seen_at"] = now
    defaults["resolved_at"] = None
    return defaults


def alert_title_for(item: dict[str, Any]) -> str:
    kind = item["kind"]
    evidence = item.get("evidence") or {}
    target_tail = str(item.get("target", "")).partition(":")[2]
    mount = str(evidence.get("mount") or target_tail or "?")
    port = str(evidence.get("port") or target_tail or "?")
    eta = item.get("eta_days")
    eta_text = f"через ~{round(eta, 1)} дн" if eta is not None else ""

    if kind == "disk_full":
        return f"Прогноз: диск {mount} достигнет {item.get('threshold') or 100}% {eta_text}"
    if kind == "inode_full":
        return f"Прогноз: inode на {mount} закончатся {eta_text}"
    if kind == "memory_pressure":
        return f"Прогноз: память истощится {eta_text}"
    if kind == "swap_growth":
        return f"Прогноз: swap дойдёт до предела {eta_text}"
    if kind == "log_error_surge":
        return "Всплеск ошибок в логах (ускорение против базового уровня)"
    if kind == "cert_expiry":
        if evidence.get("expired"):
            return f"Сертификат на порту {port} истёк"
        return f"Сертификат на порту {port} истекает {eta_text}"
    if kind == "cert_changed":
        return f"Сертификат на порту {port} сменился"
    return f"Прогноз: {kind} {item.get('target', '')} {eta_text}"


def persist_predictions_for_server(
    server: Server,
    predictions: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Upsert active predictions and resolve the ones that disappeared."""
    now = now or timezone.now()
    summary = {"created": 0, "updated": 0, "resolved": 0}
    seen_pairs: set[tuple[str, str]] = set()

    for item in predictions:
        pair = (str(item["kind"]), str(item["target"]))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        _, created = ServerPrediction.objects.update_or_create(
            server=server,
            kind=pair[0],
            target=pair[1],
            defaults=_prediction_defaults(item, now),
        )
        summary["created" if created else "updated"] += 1

    stale = ServerPrediction.objects.filter(server=server, status=ServerPrediction.STATUS_ACTIVE)
    for row in stale:
        if (row.kind, row.target) in seen_pairs:
            continue
        row.status = ServerPrediction.STATUS_RESOLVED
        row.resolved_at = now
        row.save(update_fields=["status", "resolved_at"])
        summary["resolved"] += 1
    return summary


def sync_forecast_alerts(
    server: Server,
    predictions: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Mirror critical/warning forecasts into alerts; resolve stale ones."""
    now = now or timezone.now()
    summary = {"created": 0, "updated": 0, "resolved": 0}
    active_fingerprints: set[str] = set()

    for item in predictions:
        if item.get("severity") not in _ALERTABLE_SEVERITIES:
            continue
        fingerprint = f"forecast:{item['kind']}:{item['target']}"
        active_fingerprints.add(fingerprint)
        title = alert_title_for(item)[:255]
        message_bits = []
        if item.get("current_value") is not None:
            message_bits.append(f"Сейчас: {item['current_value']}{item.get('unit') or ''}")
        if item.get("slope_per_day") is not None:
            message_bits.append(f"Скорость: {item['slope_per_day']}/день")
        if item.get("confidence") is not None:
            message_bits.append(f"Уверенность: {round(item['confidence'] * 100)}%")
        metadata = {
            "fingerprint": fingerprint,
            "prediction_kind": item["kind"],
            "prediction_target": item["target"],
            "eta_days": item.get("eta_days"),
            "predicted_for": item.get("predicted_for"),
            "last_seen_at": now.isoformat(),
        }

        existing = None
        for row in ServerAlert.objects.filter(
            server=server, alert_type=ServerAlert.TYPE_FORECAST, is_resolved=False
        ).only("id", "metadata", "severity", "title", "message"):
            row_meta = row.metadata if isinstance(row.metadata, dict) else {}
            if str(row_meta.get("fingerprint") or "") == fingerprint:
                existing = row
                break

        if existing is None:
            ServerAlert.objects.create(
                server=server,
                alert_type=ServerAlert.TYPE_FORECAST,
                severity=item["severity"],
                title=title,
                message=" · ".join(message_bits),
                metadata=metadata,
            )
            summary["created"] += 1
        else:
            existing.severity = item["severity"]
            existing.title = title
            existing.message = " · ".join(message_bits)
            existing.metadata = {**(existing.metadata or {}), **metadata}
            existing.save(update_fields=["severity", "title", "message", "metadata"])
            summary["updated"] += 1

    stale_rows = ServerAlert.objects.filter(
        server=server, alert_type=ServerAlert.TYPE_FORECAST, is_resolved=False
    ).only("id", "metadata", "is_resolved", "resolved_at")
    for row in stale_rows:
        row_meta = row.metadata if isinstance(row.metadata, dict) else {}
        fingerprint = str(row_meta.get("fingerprint") or "")
        if fingerprint in active_fingerprints:
            continue
        row.is_resolved = True
        row.resolved_at = now
        row.save(update_fields=["is_resolved", "resolved_at"])
        summary["resolved"] += 1
    return summary


def run_forecast_persistence(
    server_ids: list[int] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """One pass: compute, persist, and alert forecasts for active SSH servers."""
    now = now or timezone.now()
    qs = Server.objects.filter(is_active=True, server_type="ssh").order_by("id")
    if server_ids:
        qs = qs.filter(id__in=server_ids)

    totals = {"servers": 0, "predictions": 0, "alerts_created": 0, "alerts_resolved": 0}
    for server in qs:
        try:
            predictions = build_server_predictions(server, now=now)
            persist_predictions_for_server(server, predictions, now=now)
            alert_summary = sync_forecast_alerts(server, predictions, now=now)
        except Exception as exc:
            logger.warning("Forecast persistence failed for {}: {}", server.name, exc)
            continue
        totals["servers"] += 1
        totals["predictions"] += len(predictions)
        totals["alerts_created"] += alert_summary["created"]
        totals["alerts_resolved"] += alert_summary["resolved"]
    return totals
