from datetime import datetime
from typing import Any

from servers.agents.agent_run_report_base import (
    MAX_EVENTS,
    TERMINAL_STATUSES,
    _json_safe,
    _line_items_from_section,
    _severity_rank,
    _text,
)
from servers.agents.agent_run_report_events import (
    _event_category,
    _event_important,
    _event_phase,
    _event_severity,
    _event_summary,
    _event_title,
    _status_label,
)
from servers.agents.agent_run_report_execution import _build_execution_state
from servers.models import AgentRun, AgentRunEvent
from servers.run_events import serialize_run_event


def _build_events(run: AgentRun, event_rows: list[AgentRunEvent] | None = None) -> list[dict[str, Any]]:
    rows = event_rows
    if rows is None:
        rows = list(AgentRunEvent.objects.filter(run=run).order_by("created_at", "id")[:MAX_EVENTS])
    events = []
    for event in rows:
        payload = _json_safe(event.payload or {})
        message = _text(event.message or event.event_type, limit=1200)
        severity = _event_severity(event.event_type, payload if isinstance(payload, dict) else {})
        events.append(
            {
                **serialize_run_event(event),
                "message": message,
                "payload": payload,
                "severity": severity,
                "source": _text(str((payload or {}).get("source") or event.event_type).replace("_", " "), limit=80)
                if isinstance(payload, dict)
                else event.event_type,
                "title": _event_title(event.event_type, payload if isinstance(payload, dict) else {}, message),
                "summary": _event_summary(event.event_type, payload if isinstance(payload, dict) else {}, message),
                "phase": _event_phase(event.event_type, payload if isinstance(payload, dict) else {}),
                "category": _event_category(event.event_type),
                "important": _event_important(event.event_type, severity, payload if isinstance(payload, dict) else {}),
            }
        )
    if not events and run.started_at:
        message = "Agent run created."
        severity = "info"
        payload: dict[str, Any] = {}
        events.append(
            {
                "id": 0,
                "run_id": run.id,
                "event_type": "agent_run_created",
                "task_id": None,
                "message": message,
                "payload": payload,
                "created_at": run.started_at.isoformat(),
                "severity": severity,
                "source": "agent",
                "title": _event_title("agent_run_created", payload, message),
                "summary": _event_summary("agent_run_created", payload, message),
                "phase": _event_phase("agent_run_created", payload),
                "category": _event_category("agent_run_created"),
                "important": _event_important("agent_run_created", severity, payload),
            }
        )
    return events


def _build_logs(run: AgentRun) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for index, item in enumerate(run.commands_output or [], start=1):
        exit_code = int(item.get("exit_code") or 0)
        logs.append(
            {
                "id": f"cmd-{index}",
                "index": index,
                "kind": "command",
                "title": _text(item.get("cmd") or f"Command {index}", limit=500),
                "command": _text(item.get("cmd"), limit=2000),
                "stdout": _text(item.get("stdout")),
                "stderr": _text(item.get("stderr")),
                "exit_code": exit_code,
                "duration_ms": int(item.get("duration_ms") or 0),
                "status": "completed" if exit_code == 0 else "failed",
                "severity": "success" if exit_code == 0 else "critical",
                "timestamp": item.get("timestamp") or None,
            }
        )
    return logs


def _build_agent_steps(run: AgentRun) -> list[dict[str, Any]]:
    if run.plan_tasks:
        steps = []
        for index, task in enumerate(run.plan_tasks or [], start=1):
            status = str(task.get("status") or "pending")
            steps.append(
                {
                    "id": str(task.get("id") or f"task-{index}"),
                    "index": index,
                    "title": _text(task.get("name") or f"Task {index}", limit=200),
                    "description": _text(task.get("description"), limit=1200),
                    "command": _text(task.get("action") or ""),
                    "status": status,
                    "severity": "critical" if status == "failed" else "success" if status == "done" else "info",
                    "status_label": _status_label(status),
                    "duration_ms": _task_duration_ms(task),
                    "details": _text(task.get("result") or task.get("error") or task.get("thought"), limit=2000),
                    "error": _text(task.get("error"), limit=1200),
                    "started_at": task.get("started_at"),
                    "completed_at": task.get("completed_at"),
                }
            )
        return steps

    if run.iterations_log:
        steps = []
        for index, item in enumerate(run.iterations_log or [], start=1):
            action = item.get("action") or item.get("tool") or ""
            observation = item.get("observation") or ""
            steps.append(
                {
                    "id": f"iteration-{item.get('iteration') or index}",
                    "index": index,
                    "title": _text(action or f"Iteration {index}", limit=200),
                    "description": _text(item.get("thought"), limit=1200),
                    "command": _text(action, limit=1000),
                    "status": "completed",
                    "severity": "success",
                    "status_label": "Завершено",
                    "duration_ms": int(item.get("duration_ms") or 0),
                    "details": _text(observation, limit=2000),
                    "error": "",
                    "started_at": item.get("timestamp"),
                    "completed_at": item.get("timestamp"),
                }
            )
        return steps

    return [
        {
            "id": item["id"],
            "index": item["index"],
            "title": item["title"],
            "description": "",
            "command": item["command"],
            "status": item["status"],
            "severity": item["severity"],
            "status_label": "Завершено" if item["exit_code"] == 0 else f"Код {item['exit_code']}",
            "duration_ms": item["duration_ms"],
            "details": item["stderr"] or item["stdout"],
            "error": item["stderr"],
            "started_at": item["timestamp"],
            "completed_at": item["timestamp"],
        }
        for item in _build_logs(run)
    ]


def _task_duration_ms(task: dict[str, Any]) -> int:
    started = task.get("started_at")
    completed = task.get("completed_at")
    if not started or not completed:
        return 0
    try:
        start_dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        return max(0, int((end_dt - start_dt).total_seconds() * 1000))
    except ValueError:
        return 0


def _build_findings(
    run: AgentRun, markdown: str, logs: list[dict[str, Any]], steps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, item in enumerate(
        _line_items_from_section(markdown, ("Ключевые находки", "Обнаружения", "Findings")), start=1
    ):
        findings.append(
            {"id": f"md-finding-{index}", "title": item, "description": "", "severity": "info", "source": "report"}
        )
    for item in logs:
        if int(item.get("exit_code") or 0) != 0:
            findings.append(
                {
                    "id": f"log-{item['id']}",
                    "title": f"Команда завершилась с кодом {item['exit_code']}",
                    "description": item["title"],
                    "severity": "critical",
                    "source": "command",
                }
            )
    for step in steps:
        if step.get("status") == "failed":
            findings.append(
                {
                    "id": f"step-{step['id']}",
                    "title": f"Шаг не выполнен: {step['title']}",
                    "description": step.get("error") or step.get("details") or "",
                    "severity": "critical",
                    "source": "agent_step",
                }
            )
    return findings[:12]


def _build_risks(run: AgentRun, markdown: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks = [
        {"id": f"md-risk-{index}", "title": item, "description": "", "severity": "high"}
        for index, item in enumerate(
            _line_items_from_section(markdown, ("Проблемы и риски", "Риски", "Risks")), start=1
        )
    ]
    for finding in findings:
        if finding.get("severity") in {"critical", "fatal"}:
            risks.append(
                {
                    "id": f"risk-{finding['id']}",
                    "title": finding["title"],
                    "description": finding.get("description") or "Требуется проверка оператора.",
                    "severity": finding.get("severity") or "high",
                }
            )
    if run.status == AgentRun.STATUS_FAILED and not risks:
        risks.append(
            {
                "id": "run-failed",
                "title": "Запуск агента завершился ошибкой",
                "description": _text(run.ai_analysis or run.final_report, limit=1000),
                "severity": "critical",
            }
        )
    return risks[:10]


def _build_recommendations(run: AgentRun, markdown: str, risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [
        {
            "id": f"md-action-{index}",
            "priority": "P1" if index == 1 else "P2",
            "title": item,
            "description": "",
            "owner": "Оператор",
            "done": False,
        }
        for index, item in enumerate(
            _line_items_from_section(markdown, ("Рекомендации", "Следующие шаги", "Recommendations")), start=1
        )
    ]
    if risks and not items:
        items.append(
            {
                "id": "review-risk",
                "priority": "P1",
                "title": "Проверить проблемные шаги и повторить сбор данных",
                "description": "Сформировано автоматически по failed-командам или failed-задачам.",
                "owner": "Оператор",
                "done": False,
            }
        )
    return items[:8]


def _report_markdown_ready(run: AgentRun, markdown: str) -> bool:
    if run.status not in TERMINAL_STATUSES or not str(markdown or "").strip():
        return False
    if str(run.final_report or "").strip():
        return True
    return run.status == AgentRun.STATUS_COMPLETED and bool(str(run.ai_analysis or "").strip())


def _latest_important_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("important"):
            return event
    return events[-1] if events else None


def _phase_from_run(run: AgentRun, events: list[dict[str, Any]], report_ready: bool) -> str:
    if report_ready:
        return "ready"
    if run.status == AgentRun.STATUS_FAILED:
        return "failed"
    if run.status == AgentRun.STATUS_STOPPED:
        return "stopped"
    if run.status == AgentRun.STATUS_WAITING:
        return "waiting"
    if run.status == AgentRun.STATUS_PLAN_REVIEW:
        return "plan_review"
    if run.status == AgentRun.STATUS_PENDING:
        return "queued"
    latest = _latest_important_event(events)
    phase = str((latest or {}).get("phase") or "").strip()
    if phase and phase != "activity":
        return phase
    if run.status == AgentRun.STATUS_RUNNING:
        return "executing"
    if run.status == AgentRun.STATUS_COMPLETED:
        return "synthesizing"
    return "activity"


def _phase_progress(phase: str) -> int:
    return {
        "queued": 8,
        "starting": 18,
        "planning": 35,
        "plan_review": 42,
        "executing": 62,
        "waiting": 55,
        "synthesizing": 86,
        "delivery": 94,
        "ready": 100,
        "failed": 100,
        "stopped": 100,
        "activity": 28,
    }.get(phase, 28)


def _problem_signal_count(
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> int:
    event_count = sum(1 for event in events if _severity_rank(event.get("severity")) >= _severity_rank("warning"))
    log_count = sum(1 for item in logs if int(item.get("exit_code") or 0) != 0)
    step_count = sum(1 for item in steps if item.get("status") in {"failed", "critical"})
    return event_count + log_count + step_count


def _build_report_state(
    run: AgentRun,
    *,
    markdown: str,
    events: list[dict[str, Any]],
    logs: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    report_ready = _report_markdown_ready(run, markdown)
    phase = _phase_from_run(run, events, report_ready)
    latest = _latest_important_event(events)
    current_step = _text((latest or {}).get("title") or (latest or {}).get("message") or "", limit=240)
    problem_count = _problem_signal_count(events, logs, steps)
    execution_state = _build_execution_state(run)

    text_by_phase = {
        "queued": (
            "Запуск ожидает worker",
            "Backend создал run и поставил его в очередь. Финальный отчёт и артефакты появятся после выполнения агента.",
            "Worker заберёт запуск и начнёт сбор данных.",
        ),
        "starting": (
            "Worker поднимает выполнение",
            "Запуск уже принят в работу, идёт подготовка окружения и подключений.",
            "Агент перейдёт к планированию или сбору данных.",
        ),
        "planning": (
            "Агент готовит план",
            "Идёт построение плана проверки. Финальный отчёт ещё не сформирован.",
            "После плана начнётся выполнение задач.",
        ),
        "plan_review": (
            "План ждёт подтверждения",
            "Агент подготовил план и остановился до подтверждения оператора.",
            "Подтвердите план или остановите запуск.",
        ),
        "executing": (
            "Агент выполняет проверки",
            "Идёт сбор данных, выполнение команд и накопление доказательств для финального отчёта.",
            "После выполнения агент соберёт итоговый markdown-отчёт.",
        ),
        "waiting": (
            "Агент ждёт ответ",
            "Выполнение приостановлено, потому что агент запросил ввод оператора.",
            "Ответьте на вопрос агента, чтобы продолжить запуск.",
        ),
        "synthesizing": (
            "Агент собирает финальный отчёт",
            "Запуск дошёл до стадии подготовки результата. Артефакты появятся после сохранения markdown-отчёта.",
            "Дождитесь сохранения финального отчёта.",
        ),
        "delivery": (
            "Отчёт доставляется",
            "Финальный отчёт сформирован, выполняется доставка во внешние каналы.",
            "После доставки артефакты будут доступны в этом экране.",
        ),
        "ready": (
            "Финальный отчёт готов",
            "Структурированный отчёт сохранён. Можно смотреть вывод, события, логи и скачивать артефакты.",
            "Дополнительных действий не требуется.",
        ),
        "failed": (
            "Запуск завершился ошибкой",
            "Агент не дошёл до корректного финального отчёта. Доступны события, логи и сохранённые шаги для диагностики.",
            "Проверьте последние ошибки и перезапустите агент после исправления причины.",
        ),
        "stopped": (
            "Запуск остановлен",
            "Оператор остановил выполнение до формирования финального отчёта.",
            "При необходимости запустите агент повторно.",
        ),
    }
    headline, description, next_expected = text_by_phase.get(
        phase,
        (
            "Запуск активен",
            "Backend получает события агента. Финальный отчёт ещё не сформирован.",
            "Дождитесь следующего события агента.",
        ),
    )
    # Surface the real failure reason instead of the generic "не дошёл до отчёта":
    # the actual error (e.g. SSH connect failure) lives in ai_analysis/final_report.
    if run.status == AgentRun.STATUS_FAILED:
        reason = _text(run.ai_analysis or run.final_report or "", limit=400)
        if reason:
            low = reason.lower()
            ssh_unreachable = "ssh" in low and any(
                marker in low
                for marker in (
                    "connect call failed",
                    "connection failed",
                    "errno 111",
                    "unreachable",
                    "timed out",
                    "no route to host",
                    "connection refused",
                )
            )
            if ssh_unreachable:
                headline = "Сервер недоступен по SSH"
                description = (
                    f"Агент не смог подключиться к серверу по SSH — {reason}. "
                    "Проверьте, что на сервере запущен SSH и он доступен по указанному host:port, "
                    "а логин/ключ корректны."
                )
                next_expected = "Восстановите доступ к серверу по SSH и перезапустите агента."
            else:
                description = f"Запуск завершился ошибкой: {reason}"
    if not report_ready and problem_count:
        description = f"{description} Уже есть проблемные сигналы: {problem_count}."
    if not report_ready and _severity_rank(execution_state.get("severity")) >= _severity_rank("warning"):
        current_step = _text(execution_state.get("title") or current_step, limit=240)
        description = f"{description} {execution_state.get('description')}"
        next_expected = _text(execution_state.get("next_action") or next_expected, limit=500)
    return {
        "phase": phase,
        "report_ready": report_ready,
        "artifacts_ready": report_ready,
        "is_terminal": run.status in TERMINAL_STATUSES,
        "headline": headline,
        "description": description,
        "current_step": current_step,
        "next_expected": next_expected,
        "progress": _phase_progress(phase),
        "execution_state": execution_state,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
