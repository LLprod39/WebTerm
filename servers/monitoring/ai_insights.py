"""LLM analysis layer over collected telemetry (AI SRE verdicts).

Deterministic math (servers.monitoring.forecasting) says *when* something breaks; this
module has the LLM read the full picture per physical endpoint — metrics,
trends, forecasts, alerts, sanitized log excerpts, certificates, server
memory notes — and produce a verdict with reasoning and actions.

Cost control: a coarse context fingerprint skips re-analysis while nothing
meaningful changed, plus a max-age refresh and a per-cycle run cap.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils import timezone
from loguru import logger

from app.egress_redaction import sanitize_prompt_context_text
from servers.models import (
    Server,
    ServerAiInsight,
    ServerAlert,
    ServerCertificate,
    ServerHealthCheck,
    ServerMetricSample,
)
from servers.monitoring.forecasting import build_server_predictions

_MAX_CONTENT_CHARS = 8000
_MAX_LOG_LINES = 10

SERVER_SYSTEM_PROMPT = (
    "Ты — опытный SRE-аналитик платформы WebTerm. Тебе дают телеметрию одного Linux-сервера: "
    "текущие метрики, тренды, детерминированные прогнозы, алерты, выдержки логов, сертификаты и заметки из памяти. "
    "Твоя задача — увидеть картину целиком: связать сигналы между собой, найти неочевидные риски и дать конкретные шаги.\n"
    "Формат ответа — краткий markdown на русском:\n"
    "## Вердикт — 1-2 предложения и отдельной строкой «Уровень риска: Низкий|Средний|Высокий|Критический»\n"
    "## Наблюдения — 2-5 пунктов, связки между сигналами (почему, а не что)\n"
    "## Что сделать — приоритизированные конкретные шаги (команды допустимы)\n"
    "Не пересказывай цифры без выводов. Если всё в порядке — скажи это коротко и не выдумывай проблем."
)

FLEET_SYSTEM_PROMPT = (
    "Ты — опытный SRE-аналитик. Тебе дают сводку по флоту серверов: статусы, вердикты по каждому серверу, "
    "прогнозы и алерты. Сформируй краткий markdown-отчёт на русском:\n"
    "## Вердикт — 1-2 предложения о флоте и строка «Уровень риска: Низкий|Средний|Высокий|Критический»\n"
    "## Главные темы — до 3 сквозных проблем/паттернов\n"
    "## Сегодня — что сделать в первую очередь и на каких серверах\n"
    "Будь конкретным и кратким."
)

_VERDICT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"критич", ServerAiInsight.VERDICT_CRITICAL),
    (r"высок", ServerAiInsight.VERDICT_HIGH),
    (r"средн", ServerAiInsight.VERDICT_MEDIUM),
    (r"низк", ServerAiInsight.VERDICT_LOW),
)


def ai_insights_enabled() -> bool:
    return bool(getattr(settings, "AI_INSIGHTS_ENABLED", True))


def _max_age() -> timedelta:
    hours = int(getattr(settings, "AI_INSIGHTS_MAX_AGE_HOURS", 24) or 24)
    return timedelta(hours=max(1, hours))


def endpoint_key_for(server: Server) -> str:
    host = (server.host or "").strip().lower()
    try:
        port = int(server.port or 22)
    except (TypeError, ValueError):
        port = 22
    return f"{host}:{port}"


def _call_llm(prompt: str, *, system_prompt: str) -> tuple[str, str]:
    """Collect one LLM completion. Split out so tests can monkeypatch it."""
    from app.core.llm import LLMProvider

    provider = LLMProvider()

    async def _collect() -> str:
        chunks: list[str] = []
        async for chunk in provider.stream_chat(prompt, model="auto", system_prompt=system_prompt):
            chunks.append(chunk)
        return "".join(chunks)

    content = async_to_sync(_collect)()
    model_used = str(getattr(provider, "last_model_used", "") or "auto")
    return content[:_MAX_CONTENT_CHARS], model_used


def parse_verdict(content: str) -> str:
    lowered = (content or "").lower()
    line_match = re.search(r"уровень риска[^\n]*", lowered)
    scope = line_match.group(0) if line_match else lowered
    for pattern, verdict in _VERDICT_PATTERNS:
        if re.search(pattern, scope):
            return verdict
    return ServerAiInsight.VERDICT_UNKNOWN


def _bucket(value: float | None, size: float) -> int | None:
    if value is None:
        return None
    return int(value // size)


def _context_signature(
    *,
    health_status: str,
    sample: ServerMetricSample | None,
    predictions: list[dict[str, Any]],
    alerts: list[ServerAlert],
    certs: list[ServerCertificate],
    now: datetime,
) -> str:
    """Coarse signature: stable while nothing operationally interesting changes."""
    payload: dict[str, Any] = {"status": health_status}
    if sample:
        worst_mounts = sorted(
            (
                (str(item.get("mount")), _bucket(item.get("percent"), 5))
                for item in (sample.disk_mounts or [])
                if isinstance(item, dict)
            ),
            key=lambda pair: pair[1] or 0,
            reverse=True,
        )[:3]
        journal_err = sample.journal_err_10m or 0
        payload.update(
            {
                "cpu": _bucket(sample.cpu_percent, 15),
                "mem": _bucket(sample.memory_percent, 10),
                "swap": _bucket(sample.swap_percent, 15),
                "disks": worst_mounts,
                "zombie": bool(sample.zombie_count),
                "reboot": bool(sample.reboot_required),
                "ntp_off": sample.ntp_synchronized is False,
                "jerr": 0 if journal_err == 0 else 1 if journal_err <= 5 else 2 if journal_err <= 20 else 3,
            }
        )
    payload["predictions"] = sorted(
        (item["kind"], item["target"], round(item["eta_days"]) if item["eta_days"] is not None else -1)
        for item in predictions
    )
    payload["alerts"] = sorted({(alert.alert_type, alert.title[:40]) for alert in alerts})
    payload["certs"] = sorted(
        (
            cert.port,
            int((cert.not_after - now).days // 7) if cert.not_after else None,
            (cert.fingerprint_sha256 or "")[:8],
        )
        for cert in certs
    )
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_server_context(server: Server, *, now: datetime | None = None) -> tuple[str, str]:
    """(context_markdown, fingerprint) for one server row."""
    now = now or timezone.now()
    sample = ServerMetricSample.objects.filter(server=server).order_by("-collected_at").first()
    health = ServerHealthCheck.objects.filter(server=server).order_by("-checked_at").first()
    alerts = list(ServerAlert.objects.filter(server=server, is_resolved=False).order_by("-created_at")[:10])
    certs = list(ServerCertificate.objects.filter(server=server, is_active=True))
    predictions = build_server_predictions(server, now=now)

    lines: list[str] = [f"# Сервер {server.name} ({server.host})"]
    if server.detected_os:
        lines.append(f"ОС: {server.detected_os}")
    lines.append(f"Статус мониторинга: {health.status if health else 'нет данных'}")

    if sample:
        uptime_days = round((sample.uptime_seconds or 0) / 86400, 1)
        lines.append("## Сейчас")
        lines.append(
            f"CPU {sample.cpu_percent}% (iowait {sample.cpu_iowait_percent}%, steal {sample.cpu_steal_percent}%), "
            f"load {sample.load_1m} на {sample.cpu_count} ядер"
        )
        lines.append(
            f"RAM {sample.memory_percent}% (доступно {sample.memory_available_mb} МБ из {sample.memory_total_mb}), "
            f"swap {sample.swap_percent}%"
        )
        lines.append(
            f"Процессы: {sample.process_count} (зомби {sample.zombie_count}), fd {sample.fd_used}/{sample.fd_max}, "
            f"tcp established {sample.tcp_established}, retrans/с {sample.tcp_retrans_per_sec}"
        )
        lines.append(
            f"Журнал за 10 мин: ошибок {sample.journal_err_10m}, предупреждений {sample.journal_warn_10m}; "
            f"reboot_required={sample.reboot_required}, ntp={sample.ntp_synchronized}, uptime {uptime_days} дн"
        )
        mounts = [item for item in (sample.disk_mounts or []) if isinstance(item, dict)]
        if mounts:
            lines.append("## Диски")
            for item in mounts[:8]:
                inode = f", inode {item.get('inode_percent')}%" if item.get("inode_percent") is not None else ""
                lines.append(
                    f"- {item.get('mount')}: {item.get('percent')}% "
                    f"({item.get('used_gb')}/{item.get('total_gb')} ГБ{inode})"
                )
        top = (sample.top_processes or {}).get("by_cpu") or []
        if top:
            lines.append("## Топ процессов по CPU")
            for proc in top[:5]:
                lines.append(
                    f"- {proc.get('command')} (cpu {proc.get('cpu_percent')}%, mem {proc.get('memory_percent')}%)"
                )
    else:
        lines.append("Расширенные метрики ещё не собраны.")

    if predictions:
        lines.append("## Детерминированные прогнозы")
        for item in predictions[:8]:
            eta = f"через ~{item['eta_days']} дн" if item["eta_days"] is not None else "без ETA"
            lines.append(f"- [{item['severity']}] {item['kind']} {item['target']}: {eta}")

    if alerts:
        lines.append("## Активные алерты")
        for alert in alerts:
            lines.append(f"- [{alert.severity}] {alert.title}")

    deep = (health.raw_output or {}).get("deep") if health and isinstance(health.raw_output, dict) else None
    log_errors = (deep or {}).get("log_errors") or []
    if log_errors:
        lines.append("## Свежие ошибки из логов (санировано)")
        for raw_line in log_errors[:_MAX_LOG_LINES]:
            lines.append(f"- {sanitize_prompt_context_text(str(raw_line)).text[:200]}")

    if certs:
        lines.append("## Сертификаты")
        for cert in certs:
            days_left = round((cert.not_after - now).total_seconds() / 86400, 1) if cert.not_after else None
            changed = (
                " (недавно менялся)"
                if cert.fingerprint_changed_at and (now - cert.fingerprint_changed_at).days <= 7
                else ""
            )
            lines.append(f"- :{cert.port} {cert.subject[:80]} — осталось {days_left} дн{changed}")

    try:
        from servers.adapters.memory_store import DjangoServerMemoryStore

        card = DjangoServerMemoryStore()._get_server_card_sync(server.id)
        notes = [*card.known_risks[:3], *card.recent_incidents[:3]]
        if notes:
            lines.append("## Заметки из памяти сервера")
            lines.extend(f"- {note}" for note in notes)
    except Exception as exc:
        logger.debug("AI insights: memory card unavailable for {}: {}", server.id, exc)

    fingerprint = _context_signature(
        health_status=health.status if health else "unknown",
        sample=sample,
        predictions=predictions,
        alerts=alerts,
        certs=certs,
        now=now,
    )
    return "\n".join(lines), fingerprint


def _latest_insight(endpoint_key: str) -> ServerAiInsight | None:
    return (
        ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_SERVER, endpoint_key=endpoint_key)
        .order_by("-created_at")
        .first()
    )


def run_server_insight(
    server: Server,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> ServerAiInsight | None:
    """Analyze one endpoint; reuse the previous verdict while context is unchanged."""
    now = now or timezone.now()
    endpoint_key = endpoint_key_for(server)
    context, fingerprint = build_server_context(server, now=now)

    existing = _latest_insight(endpoint_key)
    if (
        not force
        and existing is not None
        and existing.context_fingerprint == fingerprint
        and not existing.error
        and (now - existing.created_at) < _max_age()
    ):
        return existing

    try:
        content, model_used = _call_llm(context, system_prompt=SERVER_SYSTEM_PROMPT)
    except Exception as exc:
        logger.warning("AI insights: LLM failed for {}: {}", server.name, exc)
        if force:
            return ServerAiInsight.objects.create(
                kind=ServerAiInsight.KIND_SERVER,
                server=server,
                endpoint_key=endpoint_key,
                verdict=ServerAiInsight.VERDICT_UNKNOWN,
                error=str(exc)[:500],
                context_fingerprint=fingerprint,
            )
        return None

    return ServerAiInsight.objects.create(
        kind=ServerAiInsight.KIND_SERVER,
        server=server,
        endpoint_key=endpoint_key,
        verdict=parse_verdict(content),
        content=content,
        context_fingerprint=fingerprint,
        model_used=model_used,
    )


def run_fleet_insight(*, force: bool = False, now: datetime | None = None) -> ServerAiInsight | None:
    """Fleet-level digest built from the latest per-endpoint verdicts."""
    now = now or timezone.now()
    rows = _latest_per_endpoint()
    if not rows:
        return None

    fingerprint = hashlib.sha256(
        json.dumps(sorted((row.endpoint_key, row.id) for row in rows)).encode("utf-8")
    ).hexdigest()
    existing = ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_FLEET).order_by("-created_at").first()
    if (
        not force
        and existing is not None
        and existing.context_fingerprint == fingerprint
        and (now - existing.created_at) < _max_age()
    ):
        return existing

    lines = [f"# Флот: {len(rows)} физических серверов", ""]
    for row in rows:
        name = row.server.name if row.server_id else row.endpoint_key
        lines.append(f"## {name} — вердикт {row.verdict}")
        lines.append((row.content or "")[:600])
        lines.append("")

    try:
        content, model_used = _call_llm("\n".join(lines), system_prompt=FLEET_SYSTEM_PROMPT)
    except Exception as exc:
        logger.warning("AI insights: fleet LLM failed: {}", exc)
        return None

    return ServerAiInsight.objects.create(
        kind=ServerAiInsight.KIND_FLEET,
        verdict=parse_verdict(content),
        content=content,
        context_fingerprint=fingerprint,
        model_used=model_used,
    )


def _latest_per_endpoint() -> list[ServerAiInsight]:
    rows: dict[str, ServerAiInsight] = {}
    for row in ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_SERVER, content__gt="").order_by("-created_at")[
        :500
    ]:
        rows.setdefault(row.endpoint_key, row)
    return list(rows.values())


def run_ai_insights_for_servers(
    server_ids: list[int] | None = None,
    *,
    force: bool = False,
    max_runs: int | None = None,
) -> dict[str, int]:
    """One analysis pass over active SSH endpoints (deduped by host:port)."""
    if not ai_insights_enabled():
        return {"enabled": 0, "analyzed": 0, "reused": 0, "errors": 0}

    if max_runs is None:
        max_runs = int(getattr(settings, "AI_INSIGHTS_MAX_RUNS_PER_CYCLE", 20) or 20)

    qs = Server.objects.filter(is_active=True, server_type="ssh").order_by("id")
    if server_ids:
        qs = qs.filter(id__in=server_ids)

    seen_endpoints: set[str] = set()
    summary = {"enabled": 1, "analyzed": 0, "reused": 0, "errors": 0}
    for server in qs:
        endpoint_key = endpoint_key_for(server)
        if endpoint_key in seen_endpoints:
            continue
        seen_endpoints.add(endpoint_key)
        if summary["analyzed"] >= max_runs:
            break
        before = _latest_insight(endpoint_key)
        row = run_server_insight(server, force=force)
        if row is None:
            summary["errors"] += 1
        elif before is not None and row.id == before.id:
            summary["reused"] += 1
        else:
            summary["analyzed"] += 1

    if summary["analyzed"] > 0 or force:
        run_fleet_insight(force=force)
    return summary


def serialize_insight(row: ServerAiInsight | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "kind": row.kind,
        "endpoint_key": row.endpoint_key,
        "server_id": row.server_id,
        "verdict": row.verdict,
        "content": row.content,
        "error": row.error,
        "model": row.model_used,
        "created_at": row.created_at.isoformat(),
    }


def latest_insights_by_endpoint(endpoint_keys: list[str]) -> dict[str, ServerAiInsight]:
    rows: dict[str, ServerAiInsight] = {}
    qs = ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_SERVER, endpoint_key__in=endpoint_keys).order_by(
        "-created_at"
    )
    for row in qs[:1000]:
        rows.setdefault(row.endpoint_key, row)
    return rows


def latest_fleet_insight() -> ServerAiInsight | None:
    return ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_FLEET).order_by("-created_at").first()
