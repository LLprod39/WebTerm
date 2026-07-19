from typing import Any

from django.utils import timezone

from servers.agent_run_report_artifacts import (
    _build_artifact_state_for_artifacts,
    _build_artifacts,
    _build_persisted_artifacts,
    _sync_agent_run_artifacts,
)
from servers.agent_run_report_base import (
    REPORT_SCHEMA_VERSION,
    _clean_inline_markdown,
    _duration_label,
    _json_safe,
    _overall_severity,
    _server_names,
    _severity,
    _summary_from_markdown,
    _text,
)
from servers.agent_run_report_content import (
    _build_agent_steps,
    _build_events,
    _build_findings,
    _build_logs,
    _build_recommendations,
    _build_report_state,
    _build_risks,
)
from servers.agent_run_report_events import (
    _build_delivery_state,
    _build_event_groups,
    _build_event_summary,
    _status_label,
)
from servers.agent_run_report_execution import _build_kpis, _serialize_run
from servers.models import AgentRun, AgentRunArtifact, AgentRunEvent
from servers.run_events import record_run_event


def build_agent_run_report_payload(
    run: AgentRun,
    *,
    event_rows: list[AgentRunEvent] | None = None,
    prefer_persisted_artifacts: bool = True,
) -> dict[str, Any]:
    markdown = _text(run.final_report or run.ai_analysis, limit=80_000)
    events = _build_events(run, event_rows)
    logs = _build_logs(run)
    steps = _build_agent_steps(run)
    findings = _build_findings(run, markdown, logs, steps)
    risks = _build_risks(run, markdown, findings)
    recommendations = _build_recommendations(run, markdown, risks)
    report_state = _build_report_state(run, markdown=markdown, events=events, logs=logs, steps=steps)
    fallback_summary = report_state["description"]
    summary = _summary_from_markdown(markdown, fallback_summary) if report_state["report_ready"] else fallback_summary
    servers = _server_names(run)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "title": _text(run.agent.name if run.agent_id and run.agent else "Agent run", limit=200),
        "subtitle": summary,
        "status": run.status,
        "status_label": _status_label(run.status),
        "severity": _overall_severity(run, findings, risks, logs, steps),
        "summary": summary,
        "root_cause": None,
        "markdown": markdown if report_state["report_ready"] else "",
        "meta": {
            "server": ", ".join(servers) if servers else "—",
            "window": _time_window(run),
            "analysis_duration": _duration_label(run.duration_ms),
            "finished_at": run.completed_at.isoformat() if run.completed_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
        },
        "kpis": [],
        "findings": findings,
        "risks": risks,
        "recommendations": recommendations,
    }
    report["kpis"] = _build_kpis(run, events, logs, steps, findings, risks)
    artifacts: list[dict[str, Any]] = []
    if report_state["artifacts_ready"]:
        persisted_artifacts = _build_persisted_artifacts(run) if prefer_persisted_artifacts else []
        artifacts = persisted_artifacts or _build_artifacts(
            run,
            markdown=markdown,
            events=events,
            logs=logs,
            steps=steps,
            report=report,
        )
    artifact_state = _build_artifact_state_for_artifacts(run, report_state, artifacts)
    delivery_state = _build_delivery_state(run, events, report_state)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run": _serialize_run(run),
        "report": report,
        "report_state": report_state,
        "artifact_state": artifact_state,
        "delivery_state": delivery_state,
        "event_summary": _build_event_summary(events),
        "event_groups": _build_event_groups(events),
        "events": events,
        "logs": logs,
        "agent_steps": steps,
        "artifacts": artifacts,
        "generated_at": timezone.now().isoformat(),
    }


def _time_window(run: AgentRun) -> str:
    if run.started_at and run.completed_at:
        return f"{run.started_at.isoformat()} - {run.completed_at.isoformat()}"
    if run.started_at:
        return run.started_at.isoformat()
    return "—"


def _normalize_report_items(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items[:40], start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                **item,
                "id": str(item.get("id") or f"item-{index}"),
                "title": _clean_inline_markdown(item.get("title") or ""),
                "description": _clean_inline_markdown(item.get("description") or ""),
                "severity": _severity(item.get("severity")),
            }
        )
    return normalized


def _normalize_recommendations(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items[:20], start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                **item,
                "id": str(item.get("id") or f"recommendation-{index}"),
                "priority": str(item.get("priority") or ("P1" if index == 1 else "P2")),
                "title": _clean_inline_markdown(item.get("title") or ""),
                "description": _clean_inline_markdown(item.get("description") or ""),
                "owner": _text(item.get("owner") or "Оператор", limit=120),
                "done": bool(item.get("done") or False),
            }
        )
    return normalized


def normalize_agent_run_report_payload(run: AgentRun, payload: Any | None = None) -> dict[str, Any]:
    base = build_agent_run_report_payload(run)
    saved = payload if isinstance(payload, dict) else run.report_payload if isinstance(run.report_payload, dict) else {}
    if not saved:
        return base

    report = saved.get("report") if isinstance(saved.get("report"), dict) else {}
    merged_report = {**base["report"], **_json_safe(report)}
    merged = {
        **base,
        "run": base["run"],
        "report": merged_report,
        "events": base["events"],
        "logs": base["logs"],
        "agent_steps": base["agent_steps"],
        "event_summary": base["event_summary"],
        "event_groups": base["event_groups"],
        "delivery_state": base["delivery_state"],
    }
    merged["report"]["findings"] = _normalize_report_items(merged["report"].get("findings"))
    merged["report"]["risks"] = _normalize_report_items(merged["report"].get("risks"))
    merged["report"]["recommendations"] = _normalize_recommendations(merged["report"].get("recommendations"))
    merged["report"]["severity"] = _overall_severity(
        run,
        merged["report"]["findings"],
        merged["report"]["risks"],
        merged["logs"],
        merged["agent_steps"],
    )
    merged["report"]["kpis"] = _build_kpis(
        run,
        merged["events"],
        merged["logs"],
        merged["agent_steps"],
        merged["report"]["findings"],
        merged["report"]["risks"],
    )
    markdown = _text(merged["report"].get("markdown") or run.final_report or run.ai_analysis, limit=80_000)
    report_state = _build_report_state(
        run,
        markdown=markdown,
        events=merged["events"],
        logs=merged["logs"],
        steps=merged["agent_steps"],
    )
    if report_state["report_ready"]:
        merged["report"]["markdown"] = markdown
        if not merged["report"].get("summary"):
            merged["report"]["summary"] = _summary_from_markdown(markdown, report_state["description"])
        if not merged["report"].get("subtitle"):
            merged["report"]["subtitle"] = merged["report"]["summary"]
        merged["artifacts"] = _build_persisted_artifacts(run) or _build_artifacts(
            run,
            markdown=markdown,
            events=merged["events"],
            logs=merged["logs"],
            steps=merged["agent_steps"],
            report=merged["report"],
        )
    else:
        merged["report"]["markdown"] = ""
        merged["report"]["summary"] = report_state["description"]
        merged["report"]["subtitle"] = report_state["description"]
        merged["artifacts"] = []
    merged["report_state"] = report_state
    merged["artifact_state"] = _build_artifact_state_for_artifacts(run, report_state, merged["artifacts"])
    merged["delivery_state"] = _build_delivery_state(run, merged["events"], report_state)
    merged["event_summary"] = _build_event_summary(merged["events"])
    merged["event_groups"] = _build_event_groups(merged["events"])
    return merged


def build_agent_run_events_payload(run: AgentRun, *, event_rows: list[AgentRunEvent] | None = None) -> list[dict[str, Any]]:
    return _build_events(run, event_rows)


def refresh_agent_run_report_payload(run: AgentRun) -> dict[str, Any]:
    payload = build_agent_run_report_payload(run, prefer_persisted_artifacts=False)
    if payload.get("report_state", {}).get("artifacts_ready"):
        _sync_agent_run_artifacts(run, payload.get("artifacts") or [])
        payload["artifacts"] = _build_persisted_artifacts(run)
    else:
        AgentRunArtifact.objects.filter(run=run).delete()
        payload["artifacts"] = []
    payload["artifact_state"] = _build_artifact_state_for_artifacts(
        run,
        payload.get("report_state", {}),
        payload.get("artifacts") or [],
    )
    run.report_payload = payload
    run.save(update_fields=["report_payload"])
    return run.report_payload


def record_run_event_and_refresh_report(run: AgentRun, event_type: str, payload: dict[str, Any] | None = None) -> AgentRunEvent | None:
    event = record_run_event(run.id, event_type, payload or {})
    refresh_agent_run_report_payload(run)
    return event


def build_agent_run_report_response(run: AgentRun) -> dict[str, Any]:
    payload = normalize_agent_run_report_payload(run)
    return {"success": True, **payload}

__all__ = [name for name in globals() if not name.startswith("__")]
