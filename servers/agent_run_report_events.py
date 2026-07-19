from typing import Any

from servers.agent_inputs import normalize_report_delivery
from servers.agent_run_report_base import (
    DELIVERY_EVENT_TYPES,
    _clean_inline_markdown,
    _mask_identifier,
    _severity,
    _severity_rank,
    _text,
)
from servers.models import AgentRun


def _status_label(status: str) -> str:
    return {
        "pending": "Ожидает",
        "running": "Выполняется",
        "paused": "Пауза",
        "waiting": "Ждет ответа",
        "plan_review": "Проверка плана",
        "completed": "Завершен",
        "failed": "Ошибка",
        "stopped": "Остановлен",
    }.get(str(status or ""), str(status or "unknown"))


def _event_severity(event_type: str, payload: dict[str, Any]) -> str:
    lowered = event_type.lower()
    if "failed" in lowered or "error" in lowered:
        return "critical"
    if "stopped" in lowered or "canceled" in lowered or "skipped" in lowered:
        return "warning"
    if "done" in lowered or "completed" in lowered or "sent" in lowered:
        return "success"
    return _severity(payload.get("severity") or payload.get("status"))


def _event_phase(event_type: str, payload: dict[str, Any]) -> str:
    phase = str(payload.get("phase") or "").strip()
    if phase:
        return phase[:40]
    if event_type in {"agent_run_created", "agent_dispatch_enqueued", "agent_manual_dispatch"}:
        return "queued"
    if event_type in {"agent_worker_claimed", "agent_background_started", "agent_plan_execution_started"}:
        return "starting"
    if event_type in {"agent_plan", "agent_plan_approved"}:
        return "planning"
    if event_type.startswith("agent_task_") or event_type in {"agent_action", "agent_observation", "agent_thought"}:
        return "executing"
    if event_type in {"agent_report", "agent_completed"}:
        return "synthesizing" if payload.get("interim") else "ready"
    if event_type in DELIVERY_EVENT_TYPES:
        return "delivery"
    if "failed" in event_type or "error" in event_type:
        return "failed"
    return "activity"


def _event_category(event_type: str) -> str:
    if "dispatch" in event_type or "worker" in event_type or "background" in event_type:
        return "system"
    if event_type.startswith("agent_task_"):
        return "task"
    if event_type in {"agent_action", "agent_observation", "agent_thought"}:
        return "agent"
    if event_type == "agent_report" or event_type in DELIVERY_EVENT_TYPES:
        return "report"
    if event_type.startswith("agent_control") or event_type in {"agent_user_reply", "agent_plan_approved"}:
        return "operator"
    return "agent"


def _event_title(event_type: str, payload: dict[str, Any], message: str) -> str:
    titles = {
        "agent_run_created": "Запуск создан",
        "agent_dispatch_enqueued": "Поставлен в очередь",
        "agent_manual_dispatch": "Запущен вручную",
        "agent_worker_claimed": "Worker забрал запуск",
        "agent_background_started": "Фоновый запуск начат",
        "agent_plan_execution_started": "Запуск плана начат",
        "agent_plan": "План подготовлен",
        "agent_plan_approved": "План подтверждён",
        "agent_task_start": "Задача началась",
        "agent_task_done": "Задача выполнена",
        "agent_task_failed": "Задача завершилась ошибкой",
        "agent_action": "Действие агента",
        "agent_observation": "Наблюдение агента",
        "agent_thought": "Рассуждение агента",
        "agent_pipeline_phase": "Этап пайплайна",
        "agent_report": "Формирование отчёта",
        "agent_completed": "Агент завершил запуск",
        "agent_control_stop_requested": "Остановка запрошена",
        "agent_report_delivered": "Отчёт доставлен",
        "agent_report_delivery_sent": "Отчёт доставлен",
        "agent_report_delivery_skipped": "Доставка отчёта пропущена",
        "agent_report_delivery_failed": "Доставка отчёта не удалась",
        "agent_background_failed": "Фоновый запуск упал",
    }
    if event_type == "agent_status":
        status = str(payload.get("status") or "").strip()
        return f"Статус: {_status_label(status)}" if status else "Статус обновлён"
    if event_type in {"agent_task_start", "agent_task_done", "agent_task_failed"}:
        name = str(payload.get("name") or payload.get("task_name") or "").strip()
        if name:
            return _text(name, limit=180)
    return titles.get(event_type, _clean_inline_markdown(message or event_type.replace("_", " "))) or event_type


def _event_summary(event_type: str, payload: dict[str, Any], message: str) -> str:
    if event_type == "agent_status":
        status = str(payload.get("status") or "").strip()
        iteration = payload.get("iteration")
        if iteration is not None:
            return f"{_status_label(status)} · итерация {iteration}"
        return _status_label(status) if status else message
    if event_type == "agent_pipeline_phase":
        return _text(payload.get("message") or payload.get("phase") or message, limit=500)
    if event_type == "agent_report":
        return "Генерируется черновик отчёта." if payload.get("interim") else "Финальный отчёт сформирован."
    if event_type in DELIVERY_EVENT_TYPES:
        channel = str(payload.get("channel") or "external").strip()
        channel_label = "Telegram" if channel == "telegram" else channel
        if event_type in {"agent_report_delivered", "agent_report_delivery_sent"}:
            return f"Отчёт отправлен в {channel_label}."
        if event_type == "agent_report_delivery_skipped":
            reason = str(payload.get("reason") or "").strip()
            if reason == "telegram_not_configured":
                return "Доставка в Telegram пропущена: не настроены bot token или chat id."
            return _text(payload.get("message") or f"Доставка в {channel_label} пропущена.", limit=500)
        status_code = payload.get("status_code")
        if status_code:
            return f"Доставка в {channel_label} завершилась ошибкой HTTP {status_code}."
        return _text(payload.get("error") or payload.get("message") or f"Доставка в {channel_label} завершилась ошибкой.", limit=500)
    if event_type in {"agent_action", "agent_observation", "agent_thought"}:
        return _text(message, limit=500)
    if event_type.startswith("agent_task_"):
        result = payload.get("result") or payload.get("error") or payload.get("description") or message
        return _text(result, limit=500)
    return _text(payload.get("message") or message, limit=500)


def _event_important(event_type: str, severity: str, payload: dict[str, Any]) -> bool:
    if _severity_rank(severity) >= _severity_rank("warning"):
        return True
    if event_type in {
        "agent_run_created",
        "agent_dispatch_enqueued",
        "agent_worker_claimed",
        "agent_background_started",
        "agent_manual_dispatch",
        "agent_pipeline_phase",
        "agent_plan",
        "agent_plan_approved",
        "agent_task_start",
        "agent_task_done",
        "agent_task_failed",
        "agent_report",
        "agent_completed",
        "agent_report_delivered",
        "agent_report_delivery_sent",
        "agent_report_delivery_skipped",
        "agent_report_delivery_failed",
        "agent_control_stop_requested",
        "agent_background_failed",
    }:
        return True
    if event_type == "agent_status":
        return str(payload.get("status") or "") in {"connecting", "planning", "running", "waiting", "failed", "completed"}
    return False


EVENT_PHASE_LABELS = {
    "queued": "Очередь",
    "starting": "Старт",
    "planning": "Планирование",
    "plan_review": "Подтверждение",
    "executing": "Выполнение",
    "waiting": "Ожидание",
    "synthesizing": "Отчёт",
    "delivery": "Доставка",
    "ready": "Готово",
    "failed": "Ошибка",
    "stopped": "Остановлен",
    "activity": "Активность",
}


def _event_bucket(events: list[dict[str, Any]], predicate) -> list[dict[str, Any]]:
    return [event for event in events if predicate(event)]


def _build_event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    important = _event_bucket(events, lambda event: bool(event.get("important")))
    problems = _event_bucket(events, lambda event: _severity_rank(event.get("severity")) >= _severity_rank("warning"))
    debug = _event_bucket(events, lambda event: bool(event.get("payload")))
    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    for event in events:
        category = str(event.get("category") or "agent")
        severity = _severity(event.get("severity"))
        categories[category] = categories.get(category, 0) + 1
        severities[severity] = severities.get(severity, 0) + 1

    latest = events[-1] if events else None
    latest_important = important[-1] if important else latest
    return {
        "total": len(events),
        "important": len(important),
        "problems": len(problems),
        "debug": len(debug),
        "categories": categories,
        "severities": severities,
        "latest": latest,
        "latest_important": latest_important,
    }


def _build_event_groups(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for event in events:
        phase = str(event.get("phase") or "activity")
        current = groups[-1] if groups else None
        if not current or current.get("phase") != phase:
            current = {
                "phase": phase,
                "label": EVENT_PHASE_LABELS.get(phase, phase),
                "count": 0,
                "important": 0,
                "problems": 0,
                "first_at": event.get("created_at"),
                "last_at": event.get("created_at"),
                "events": [],
            }
            groups.append(current)
        current["count"] += 1
        current["last_at"] = event.get("created_at")
        if event.get("important"):
            current["important"] += 1
        if _severity_rank(event.get("severity")) >= _severity_rank("warning"):
            current["problems"] += 1
        current["events"].append(event)
    return groups


def _build_delivery_state(run: AgentRun, events: list[dict[str, Any]], report_state: dict[str, Any]) -> dict[str, Any]:
    delivery = normalize_report_delivery(run.agent.report_delivery if run.agent_id and run.agent else {})
    telegram = delivery.get("telegram") or {}
    enabled_channels = []
    if telegram.get("enabled"):
        enabled_channels.append("telegram")
    delivery_events = [event for event in events if event.get("event_type") in DELIVERY_EVENT_TYPES]
    latest = delivery_events[-1] if delivery_events else None
    target = _mask_identifier(telegram.get("chat_id"))
    base = {
        "enabled": bool(enabled_channels),
        "channels": enabled_channels,
        "channel": str((latest or {}).get("payload", {}).get("channel") or (enabled_channels[0] if enabled_channels else "")),
        "target": target,
        "status": "disabled",
        "severity": "info",
        "label": "Выключена",
        "title": "Внешняя доставка выключена",
        "description": "Отчёт доступен в UI и в downloadable artifacts.",
        "next_action": "",
        "updated_at": None,
        "event": latest,
    }

    if latest:
        event_type = str(latest.get("event_type") or "")
        payload = latest.get("payload") if isinstance(latest.get("payload"), dict) else {}
        base.update(
            {
                "channel": str(payload.get("channel") or base["channel"] or "external"),
                "target": _text(payload.get("chat_id") or payload.get("target") or base["target"], limit=120),
                "updated_at": latest.get("created_at"),
                "event": latest,
            }
        )
        if event_type in {"agent_report_delivered", "agent_report_delivery_sent"}:
            base.update(
                {
                    "enabled": True,
                    "status": "sent",
                    "severity": "success",
                    "label": "Доставлено",
                    "title": "Отчёт доставлен",
                    "description": latest.get("summary") or "Отчёт успешно отправлен во внешний канал.",
                    "next_action": "",
                }
            )
            return base
        if event_type == "agent_report_delivery_skipped":
            reason = str(payload.get("reason") or "")
            next_action = "Настройте Telegram bot token и chat id или выключите доставку для агента."
            if reason and reason != "telegram_not_configured":
                next_action = "Проверьте настройки доставки отчёта."
            base.update(
                {
                    "enabled": True,
                    "status": "skipped",
                    "severity": "warning",
                    "label": "Пропущено",
                    "title": "Доставка отчёта пропущена",
                    "description": latest.get("summary") or latest.get("message") or "Доставка отчёта была пропущена.",
                    "next_action": next_action,
                }
            )
            return base
        if event_type == "agent_report_delivery_failed":
            base.update(
                {
                    "enabled": True,
                    "status": "failed",
                    "severity": "critical",
                    "label": "Ошибка",
                    "title": "Доставка отчёта не удалась",
                    "description": latest.get("summary") or latest.get("message") or "Внешний канал вернул ошибку доставки.",
                    "next_action": "Проверьте настройки канала и повторите отправку отчёта после исправления причины.",
                }
            )
            return base

    if not enabled_channels:
        return base
    if not report_state.get("report_ready"):
        base.update(
            {
                "status": "waiting_report",
                "severity": "info",
                "label": "Ждёт отчёт",
                "title": "Доставка ждёт финальный отчёт",
                "description": "Внешняя доставка включена, но финальный отчёт ещё не сформирован.",
                "next_action": "Дождитесь завершения агента.",
            }
        )
        return base
    base.update(
        {
            "status": "pending",
            "severity": "warning",
            "label": "Ожидает",
            "title": "Доставка ещё не подтверждена",
            "description": "Финальный отчёт готов, но событие успешной доставки ещё не записано.",
            "next_action": "Проверьте worker и настройки доставки отчёта.",
        }
    )
    return base

__all__ = [name for name in globals() if not name.startswith("__")]
