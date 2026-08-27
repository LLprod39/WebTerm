from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

from app.agent_kernel.memory.redaction import sanitize_observation_text
from core_ui.services.notification_config import load_notification_config
from servers.agents.agent_inputs import normalize_report_delivery
from servers.agents.agent_run_report_base import (
    DELIVERY_EVENT_TYPES,
    TERMINAL_STATUSES,
    _bytes_label,
    _duration_label,
    _json_safe,
    _mask_identifier,
    _severity,
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
from servers.models import AgentRun, AgentRunArtifact, AgentRunEvent
from servers.run_events import serialize_run_event
from servers.services.agent_audit import verify_agent_audit_chain

REPORT_V2_SCHEMA_VERSION = 2
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
DOCUMENT_PREVIEW_CHARS = 800
_SENSITIVE_KEY_MARKERS = (
    "access_token",
    "api_key",
    "authorization",
    "bot_token",
    "cookie",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
)
_OUTCOME_LABELS = {
    "success": "Успех",
    "partial": "Частично выполнено",
    "failed": "Ошибка",
    "stopped": "Остановлено",
    "running": "Выполняется",
    "inconclusive": "Недостаточно данных для вывода",
    "unknown": "Нет подтверждённого результата",
}
_OUTCOME_SEVERITIES = {
    "success": "success",
    "partial": "warning",
    "failed": "critical",
    "stopped": "warning",
    "running": "info",
    "inconclusive": "warning",
    "unknown": "info",
}
_RU_NUMBER_WORDS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "одного": 1,
    "одной": 1,
    "два": 2,
    "две": 2,
    "двух": 2,
    "три": 3,
    "трех": 3,
    "трёх": 3,
    "четыре": 4,
    "четырех": 4,
    "четырёх": 4,
    "пять": 5,
    "пяти": 5,
}


def _public_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_observation_text(value).text.strip()
    if isinstance(value, list):
        return [_public_value(item) for item in value[:100]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            safe_key = str(key)
            lowered = safe_key.lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                result[safe_key] = "[REDACTED]"
            elif lowered in {"chat_id", "telegram_chat_id"}:
                result[safe_key] = _mask_identifier(item)
            else:
                result[safe_key] = _public_value(item)
        return result
    return value


def redacted_full_document(run: AgentRun) -> str:
    return sanitize_observation_text(str(run.final_report or run.ai_analysis or "")).text.strip()


def _document_metadata(run: AgentRun) -> dict[str, Any]:
    content = redacted_full_document(run)
    encoded = content.encode("utf-8", errors="replace")
    detail_url = f"/servers/api/agents/runs/{run.id}/report/document/"
    return {
        "available": bool(content),
        "title": f"agent-run-{run.id}-report.md",
        "content_type": "text/markdown; charset=utf-8",
        "size_bytes": len(encoded),
        "size_label": _bytes_label(len(encoded)),
        "checksum_sha256": hashlib.sha256(encoded).hexdigest() if content else "",
        "preview": content[:DOCUMENT_PREVIEW_CHARS],
        "preview_truncated": len(content) > DOCUMENT_PREVIEW_CHARS,
        "detail_url": detail_url if content else "",
        "download_url": f"{detail_url}?download=1" if content else "",
    }


def _legacy_outcome_from_document(document: str) -> tuple[str, str]:
    matches = re.findall(
        r"^Outcome:\s*(success|partial|failed|stopped)\s*(?:[—:-]\s*(.*))?$",
        document,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not matches:
        return "", ""
    status, reason = matches[-1]
    return status.lower(), _text(reason, limit=2_000)


def _outcome_for_run(run: AgentRun, document: str, coverage: dict[str, Any]) -> dict[str, Any]:
    stored = run.execution_outcome if isinstance(run.execution_outcome, dict) else {}
    saved = run.report_payload if isinstance(run.report_payload, dict) else {}
    saved_details = saved.get("outcome_details") if isinstance(saved.get("outcome_details"), dict) else {}
    saved_report = saved.get("report") if isinstance(saved.get("report"), dict) else {}
    document_outcome, document_reason = _legacy_outcome_from_document(document)
    outcome = (
        str(
            stored.get("outcome")
            or saved.get("outcome")
            or saved_details.get("outcome")
            or saved_report.get("outcome")
            or document_outcome
            or ""
        )
        .strip()
        .lower()
    )
    reason = _text(
        stored.get("reason")
        or saved.get("outcome_reason")
        or saved_details.get("reason")
        or saved_report.get("outcome_reason")
        or document_reason
        or (run.ai_analysis if run.status in {AgentRun.STATUS_FAILED, AgentRun.STATUS_STOPPED} else ""),
        limit=2_000,
    )
    source = "kernel" if stored.get("outcome") else "legacy_inference"
    if outcome not in _OUTCOME_LABELS:
        if run.status == AgentRun.STATUS_FAILED:
            outcome = "failed"
        elif run.status == AgentRun.STATUS_STOPPED:
            outcome = "stopped"
        elif run.status in TERMINAL_STATUSES:
            outcome = "unknown"
        else:
            outcome = "running"
    exit_reason = _text(stored.get("exit_reason") or saved_details.get("exit_reason") or "", limit=120)
    if not exit_reason and reason.lower() == "llm call failed":
        exit_reason = "llm_error"
    elif not exit_reason and "stale runtime threshold" in reason.lower():
        exit_reason = "stale_cleanup"
    detail_keys = (
        "tool_call_count",
        "failed_task_count",
        "done_task_count",
        "skipped_task_count",
        "pending_task_count",
        "pending_verifications",
        "plan_summary",
        "verification_summary",
        "policy_blocked_count",
        "disconnected_servers",
    )
    details = {key: stored[key] for key in detail_keys if key in stored}
    if not details:
        details = {key: saved_details[key] for key in detail_keys if key in saved_details}
    technical_outcome = outcome
    technical_reason = reason
    explicit_partial = bool(re.search(r"(?:статус[^\n]{0,40}частич|partial\s+success)", document, flags=re.IGNORECASE))
    partial_coverage = bool(
        coverage.get("total")
        and coverage.get("checked") is not None
        and int(coverage["checked"]) < int(coverage["total"])
    )
    if outcome == "failed" and document and exit_reason == "llm_error" and (explicit_partial or partial_coverage):
        outcome = "partial"
        source = "kernel_and_report"
        details = {
            **details,
            "technical_outcome": technical_outcome,
            "technical_reason": technical_reason,
        }
        if partial_coverage:
            reason = (
                f"Проверено {coverage['checked']} из {coverage['total']} {coverage.get('unit') or 'объектов'}; "
                f"техническое завершение: {technical_reason or exit_reason}."
            )
    elif outcome == "unknown" and document:
        outcome = "inconclusive"
    return {
        "status": outcome,
        "label": _OUTCOME_LABELS[outcome],
        "reason": reason,
        "exit_reason": exit_reason,
        "source": source,
        "reason_source": source,
        "severity": _OUTCOME_SEVERITIES[outcome],
        "details": _public_value(details),
    }


def _lifecycle(run: AgentRun) -> dict[str, Any]:
    active = run.status not in TERMINAL_STATUSES
    return {
        "status": run.status,
        "label": _status_label(run.status),
        "is_active": active,
        "is_terminal": not active,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": int(run.duration_ms or 0),
        "duration_label": _duration_label(run.duration_ms),
    }


def _parse_number(value: str) -> int | None:
    raw = str(value or "").strip().lower()
    if raw.isdigit():
        return int(raw)
    return _RU_NUMBER_WORDS.get(raw)


def _coverage(document: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", document.lower())
    checked: int | None = None
    total: int | None = None
    direct = re.search(r"\b(\d+)\s*(?:/|из)\s*(\d+)\b", compact)
    if direct:
        checked, total = int(direct.group(1)), int(direct.group(2))
    if checked is None:
        words = "|".join([r"\d+", *map(re.escape, _RU_NUMBER_WORDS)])
        contextual = re.search(
            rf"(?:провер\w*|исследован\w*)[^.\n]{{0,100}}?(?:у\s+)?({words})\s+(?:контейнер\w*\s+)?из\s+(\d+)",
            compact,
        )
        if contextual:
            checked = _parse_number(contextual.group(1))
            total = int(contextual.group(2))
    unit = "контейнеров" if "контейнер" in compact else "объектов"
    ratio = round(checked / total, 4) if checked is not None and total else None
    return {"checked": checked, "total": total, "unit": unit, "ratio": ratio}


def _markdown_sections(document: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = OrderedDict()
    current = ""
    for raw_line in document.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = re.sub(r"\s+", " ", heading.group(1)).strip().lower()
            current = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", current)
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def _atomic_bullets(lines: Iterable[str]) -> list[str]:
    items: list[str] = []
    for raw in lines:
        line = str(raw or "").strip()
        if not line or line == "---" or line.startswith("**Статус:") or line.startswith("Outcome:"):
            continue
        if re.match(r"^[-*+]\s+", line):
            line = re.sub(r"^[-*+]\s+", "", line, count=1)
        elif re.match(r"^\d+[.)]\s+", line):
            line = re.sub(r"^\d+[.)]\s+", "", line, count=1)
        else:
            continue
        for part in re.split(r"(?<=[.!?])\s*-\s+", line):
            cleaned = re.sub(r"\s+", " ", part).strip(" -*")
            cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
            if cleaned and cleaned != "--" and not cleaned.lower().startswith("статус:"):
                items.append(_text(cleaned, limit=1_500))
    return items


def _atomic_recommendations(lines: Iterable[str]) -> list[str]:
    """Extract legacy recommendations without treating code as an executable action."""

    source_lines = list(lines)
    bullets = _atomic_bullets(source_lines)
    if bullets:
        return bullets

    items: list[str] = []
    inside_code = False
    for raw in source_lines:
        line = str(raw or "").strip()
        if line.startswith("```"):
            if line.count("```") < 2:
                inside_code = not inside_code
            continue
        if inside_code or not line or line == "---":
            continue
        cleaned = re.sub(r"\s+", " ", line).strip(" -*:")
        cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
        if len(cleaned) >= 12:
            items.append(_text(cleaned, limit=1_500))
    return items


def _stable_item_id(prefix: str, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _document_ref(run_id: int, section: str, index: int, label: str) -> dict[str, Any]:
    ref = f"document:{section}:{index}"
    return {
        "kind": "document",
        "ref": ref,
        "label": label,
        "href": f"/agents/run/{run_id}?tab=evidence&view=document&evidence={ref}",
    }


def _activity_ref(run_id: int, item: dict[str, Any], label: str = "Открыть действие") -> dict[str, Any]:
    ref = f"activity:{item['id']}"
    return {
        "kind": "activity",
        "ref": ref,
        "label": label,
        "href": f"/agents/run/{run_id}?tab=evidence&view=activity&evidence={item['id']}",
    }


def _evidence_registry(
    run: AgentRun,
    events: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    *,
    document_available: bool,
) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        ref = f"event:{event_id}"
        registry[ref] = {
            "kind": "event",
            "ref": ref,
            "label": _text(event.get("title") or "Открыть событие", limit=120),
            "href": f"/agents/run/{run.id}?tab=evidence&view=events&evidence={event_id}",
        }
    for item in activities:
        ref = _activity_ref(run.id, item)
        registry[ref["ref"]] = ref
    for artifact in AgentRunArtifact.objects.filter(run=run).only("id", "artifact_key", "name"):
        ref = f"artifact:{artifact.id}"
        canonical = {
            "kind": "artifact",
            "ref": ref,
            "label": _text(artifact.name or "Открыть файл", limit=120),
            "href": f"/agents/run/{run.id}?tab=evidence&view=artifacts&evidence={artifact.id}",
        }
        registry[ref] = canonical
        if artifact.artifact_key:
            registry[f"artifact:{artifact.artifact_key}"] = {**canonical, "ref": f"artifact:{artifact.artifact_key}"}
    if document_available:
        registry["document"] = {
            "kind": "document",
            "ref": "document",
            "label": "Открыть полный отчёт",
            "href": f"/agents/run/{run.id}?tab=evidence&view=document&evidence=document",
        }
    return registry


def _validated_evidence_refs(
    raw_refs: Any,
    registry: dict[str, dict[str, Any]],
    *,
    run_id: int,
    document_available: bool,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(raw_refs, list):
        return refs
    for raw in raw_refs[:20]:
        raw_ref = raw if isinstance(raw, str) else raw.get("ref") if isinstance(raw, dict) else ""
        ref_value = str(raw_ref or "").strip()
        if not ref_value or ref_value in seen:
            continue
        canonical = registry.get(ref_value)
        if canonical is None and document_available and ref_value.startswith("document:"):
            canonical = {
                "kind": "document",
                "ref": ref_value[:200],
                "label": _text(raw.get("label") if isinstance(raw, dict) else "Открыть полный отчёт", limit=120)
                or "Открыть полный отчёт",
                "href": f"/agents/run/{run_id}?tab=evidence&view=document&evidence={ref_value[:200]}",
            }
        if canonical is None:
            continue
        seen.add(ref_value)
        refs.append(dict(canonical))
    return refs


def _validated_model_indicators(
    run: AgentRun,
    registry: dict[str, dict[str, Any]],
    *,
    document_available: bool,
) -> list[dict[str, Any]]:
    payload = run.report_payload if isinstance(run.report_payload, dict) else {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    model_report = payload.get("model_report") if isinstance(payload.get("model_report"), dict) else {}
    candidates = model_report.get("indicators") or report.get("indicators") or report.get("domain_indicators")
    raw_items = candidates if isinstance(candidates, list) else []
    allowed_roles = {"primary", "supporting"}
    allowed_value_kinds = {"status", "duration", "ratio", "count", "text", "number"}
    allowed_tones = {"success", "info", "warning", "high", "critical", "fatal"}
    indicators: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items[:12], start=1):
        if not isinstance(raw, dict):
            continue
        label = _text(raw.get("label"), limit=120)
        value = _text(raw.get("value"), limit=160)
        value_kind = str(raw.get("value_kind") or "text").strip().lower()
        tone = str(raw.get("tone") or "info").strip().lower()
        if not label or not value or value_kind not in allowed_value_kinds or tone not in allowed_tones:
            continue
        try:
            priority = max(1, min(int(raw.get("priority") or 10), 100))
        except (TypeError, ValueError):
            priority = 10
        refs = _validated_evidence_refs(
            raw.get("evidence_refs"),
            registry,
            run_id=run.id,
            document_available=document_available,
        )
        indicators.append(
            {
                "id": _text(raw.get("id") or f"model-{index}", limit=80),
                "role": str(raw.get("role") or "supporting")
                if str(raw.get("role") or "supporting") in allowed_roles
                else "supporting",
                "label": label,
                "value": value,
                "value_kind": value_kind,
                "unit": _text(raw.get("unit"), limit=40),
                "numerator": raw.get("numerator") if isinstance(raw.get("numerator"), (int, float)) else None,
                "denominator": raw.get("denominator") if isinstance(raw.get("denominator"), (int, float)) else None,
                "tone": tone,
                "priority": priority,
                "evidence_refs": refs,
            }
        )
    return indicators


def _confidence(value: Any) -> str | float:
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    normalized = str(value or "reported").strip().lower()
    return normalized if normalized in {"low", "medium", "high", "reported", "unknown"} else "reported"


def _structured_report_lists(run: AgentRun) -> tuple[list[Any], list[Any], list[Any]]:
    payload = run.report_payload if isinstance(run.report_payload, dict) else {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    model_report = payload.get("model_report") if isinstance(payload.get("model_report"), dict) else {}

    def merged(*values: Any) -> list[Any]:
        result: list[Any] = []
        for value in values:
            if isinstance(value, list):
                result.extend(value)
        return result

    def explicitly_structured(value: Any, *, action: bool = False) -> list[Any]:
        if not isinstance(value, list):
            return []
        markers = {"evidence_refs"}
        markers.update({"cta", "safety"} if action else {"confidence", "scope"})
        structured_sources = {"kernel", "llm", "model", "structured_report"}
        return [
            item
            for item in value
            if isinstance(item, dict)
            and (
                any(marker in item for marker in markers)
                or str(item.get("source") or "").strip().lower() in structured_sources
            )
        ]

    return (
        merged(
            model_report.get("findings"),
            report.get("model_findings"),
            explicitly_structured(report.get("findings")),
        ),
        merged(
            model_report.get("risks"),
            report.get("model_risks"),
            explicitly_structured(report.get("risks")),
        ),
        merged(
            model_report.get("actions"),
            model_report.get("recommendations"),
            report.get("actions"),
            report.get("model_actions"),
            explicitly_structured(report.get("recommendations"), action=True),
        ),
    )


def _atomic_findings_and_actions(
    run: AgentRun,
    document: str,
    registry: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    structured_findings, structured_risks, structured_actions = _structured_report_lists(run)
    document_available = bool(document)
    findings: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    seen_findings: set[str] = set()
    seen_actions: set[str] = set()

    for kind, raw_items, fallback_severity, section in (
        ("finding", structured_findings, "info", "findings"),
        ("risk", structured_risks, "high", "risks"),
    ):
        for index, raw in enumerate(raw_items[:40], start=1):
            if not isinstance(raw, dict):
                continue
            title = _text(raw.get("title") or raw.get("summary"), limit=1_500)
            if not title:
                continue
            dedupe_key = re.sub(r"\s+", " ", title).casefold()
            if dedupe_key in seen_findings:
                continue
            refs = _validated_evidence_refs(
                raw.get("evidence_refs"),
                registry,
                run_id=run.id,
                document_available=document_available,
            )
            if not refs and document_available:
                refs = [_document_ref(run.id, section, index, "Открыть в полном отчёте")]
            seen_findings.add(dedupe_key)
            description = _text(raw.get("description"), limit=2_000)
            details = _text(raw.get("details"), limit=3_000)
            findings.append(
                {
                    "id": _text(raw.get("id") or _stable_item_id(kind, title), limit=120),
                    "kind": kind,
                    "title": title,
                    "summary": _text(raw.get("summary") or title, limit=1_500),
                    "description": description,
                    "details": details,
                    "severity": _severity(raw.get("severity") or fallback_severity),
                    "source": _text(raw.get("source") or "structured_report", limit=80),
                    "confidence": _confidence(raw.get("confidence")),
                    "scope": _text(
                        raw.get("scope") or (run.server.name if run.server_id and run.server else "run"),
                        limit=160,
                    ),
                    "evidence_refs": refs,
                }
            )

    for index, raw in enumerate(structured_actions[:40], start=1):
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title") or raw.get("summary"), limit=1_500)
        if not title:
            continue
        dedupe_key = re.sub(r"\s+", " ", title).casefold()
        if dedupe_key in seen_actions:
            continue
        refs = _validated_evidence_refs(
            raw.get("evidence_refs"),
            registry,
            run_id=run.id,
            document_available=document_available,
        )
        if not refs and document_available:
            refs = [_document_ref(run.id, "recommendations", index, "Источник рекомендации")]
        cta_raw = raw.get("cta") if isinstance(raw.get("cta"), dict) else {}
        cta_ref = str(cta_raw.get("ref") or "")
        canonical_cta_ref = next((ref for ref in refs if ref.get("ref") == cta_ref), None) if cta_ref else None
        canonical_cta_ref = canonical_cta_ref or (refs[0] if refs else None)
        cta_type = str(cta_raw.get("type") or ("open_evidence" if canonical_cta_ref else "none"))
        if cta_type not in {"open_evidence", "open_url", "rerun", "configure_delivery", "none"}:
            cta_type = "open_evidence" if canonical_cta_ref else "none"
        supplied_href = _text(cta_raw.get("href"), limit=500)
        safe_supplied_href = (
            supplied_href if supplied_href.startswith("/") and not supplied_href.startswith("//") else ""
        )
        cta_href = (canonical_cta_ref or {}).get("href") or safe_supplied_href
        safety = str(raw.get("safety") or "review_required").strip().lower()
        if safety not in {"read_only", "review_required", "destructive", "unknown"}:
            safety = "review_required"
        status = str(raw.get("status") or ("done" if raw.get("done") else "pending")).strip().lower()
        if status not in {"pending", "in_progress", "done", "blocked"}:
            status = "pending"
        seen_actions.add(dedupe_key)
        actions.append(
            {
                "id": _text(raw.get("id") or _stable_item_id("action", title), limit=120),
                "title": title,
                "summary": _text(raw.get("summary") or title, limit=1_500),
                "description": _text(raw.get("description"), limit=2_000),
                "details": _text(raw.get("details"), limit=3_000),
                "priority": str(raw.get("priority") or ("P1" if index == 1 else "P2"))[:8],
                "status": status,
                "owner": _text(raw.get("owner") or "Оператор", limit=120),
                "safety": safety,
                "evidence_refs": refs,
                "cta": {
                    "type": cta_type,
                    "label": _text(cta_raw.get("label") or ("Открыть доказательство" if cta_href else ""), limit=120),
                    "ref": str((canonical_cta_ref or {}).get("ref") or ""),
                    "href": cta_href,
                    "enabled": bool(cta_href and cta_type != "none"),
                },
            }
        )

    sections = _markdown_sections(document)
    finding_lines: list[str] = []
    risk_lines: list[str] = []
    action_lines: list[str] = []
    for heading, lines in sections.items():
        if heading in {"ключевые находки", "обнаружения", "findings"}:
            finding_lines.extend(_atomic_bullets(lines))
        elif heading in {"проблемы и риски", "риски", "risks"}:
            risk_lines.extend(_atomic_bullets(lines))
        elif heading in {"рекомендации", "следующие шаги", "recommendations"}:
            action_lines.extend(_atomic_recommendations(lines))

    for kind, values, severity, section in (
        ("finding", finding_lines, "info", "findings"),
        ("risk", risk_lines, "high", "risks"),
    ):
        for index, title in enumerate(values, start=1):
            dedupe_key = re.sub(r"\s+", " ", title).casefold()
            if dedupe_key in seen_findings:
                continue
            seen_findings.add(dedupe_key)
            findings.append(
                {
                    "id": _stable_item_id(kind, title),
                    "kind": kind,
                    "title": title,
                    "summary": "",
                    "description": "",
                    "details": "",
                    "severity": severity,
                    "source": "report_document",
                    "confidence": "reported",
                    "scope": _text(run.server.name if run.server_id and run.server else "run", limit=160),
                    "evidence_refs": [_document_ref(run.id, section, index, "Открыть в полном отчёте")],
                }
            )

    for index, title in enumerate(action_lines, start=1):
        dedupe_key = re.sub(r"\s+", " ", title).casefold()
        if dedupe_key in seen_actions:
            continue
        seen_actions.add(dedupe_key)
        evidence = _document_ref(run.id, "recommendations", index, "Источник рекомендации")
        actions.append(
            {
                "id": _stable_item_id("action", title),
                "title": title,
                "summary": "",
                "description": "",
                "details": "",
                "priority": "P1" if index == 1 else "P2",
                "status": "pending",
                "owner": "Оператор",
                "safety": "review_required",
                "evidence_refs": [evidence],
                "cta": {
                    "type": "open_evidence",
                    "label": "Открыть доказательство",
                    "ref": evidence["ref"],
                    "href": evidence["href"],
                    "enabled": True,
                },
            }
        )
    return findings[:24], actions[:16]


def _public_event(event: AgentRunEvent) -> dict[str, Any]:
    payload = _public_value(_json_safe(event.payload or {}))
    payload = payload if isinstance(payload, dict) else {}
    message = _text(event.message or event.event_type, limit=1_200)
    severity = _event_severity(event.event_type, payload)
    serialized = serialize_run_event(event)
    serialized.pop("integrity", None)
    return {
        **serialized,
        "payload": payload,
        "message": message,
        "severity": severity,
        "source": _text(str(payload.get("source") or event.event_type).replace("_", " "), limit=80),
        "title": _event_title(event.event_type, payload, message),
        "summary": _event_summary(event.event_type, payload, message),
        "phase": _event_phase(event.event_type, payload),
        "category": _event_category(event.event_type),
        "important": _event_important(event.event_type, severity, payload),
    }


def _all_public_events(run: AgentRun) -> list[dict[str, Any]]:
    rows = AgentRunEvent.objects.filter(run=run).order_by("sequence_no", "id")
    return [_public_event(row) for row in rows.iterator(chunk_size=500)]


def _event_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    important = sum(1 for event in events if event.get("important"))
    delivery_problems = sum(
        1
        for event in events
        if event.get("event_type") in DELIVERY_EVENT_TYPES
        and _severity_rank(event.get("severity")) >= _severity_rank("warning")
    )
    execution_problems = sum(
        1
        for event in events
        if event.get("event_type") not in DELIVERY_EVENT_TYPES
        and _severity_rank(event.get("severity")) >= _severity_rank("warning")
    )
    return {
        "events_total": len(events),
        "important_events": important,
        "execution_problem_events": execution_problems,
        "delivery_problem_events": delivery_problems,
    }


def _phase_summary(
    run: AgentRun,
    events: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    lifecycle: dict[str, Any],
    outcome: dict[str, Any],
) -> list[dict[str, Any]]:
    """Presentation phases are stable; raw runtime phases remain on event items."""
    goal_text = _text(
        (run.agent.goal or run.agent.ai_prompt) if run.agent_id and run.agent else "Выполнить назначенную проверку.",
        limit=1_200,
    )
    problem_events = [event for event in events if _severity_rank(event.get("severity")) >= _severity_rank("warning")]
    important_events = [event for event in events if event.get("important")]
    failed_activities = [item for item in activities if item.get("status") == "failed"]

    observation_items = []
    for finding in findings[:3]:
        observation_items.append(
            {
                "id": str(finding.get("id") or ""),
                "kind": str(finding.get("kind") or "finding"),
                "title": _text(finding.get("title"), limit=240),
                "summary": _text(finding.get("summary") or finding.get("description"), limit=500),
                "severity": str(finding.get("severity") or "info"),
                "evidence_ref": (finding.get("evidence_refs") or [None])[0],
            }
        )
    for event in [*problem_events, *important_events]:
        event_id = str(event.get("id") or "")
        if not event_id or any(item.get("id") == event_id for item in observation_items):
            continue
        observation_items.append(
            {
                "id": event_id,
                "kind": str(event.get("category") or "event"),
                "title": _text(event.get("title") or event.get("event_type") or "Событие", limit=240),
                "summary": _text(event.get("summary") or event.get("message"), limit=500),
                "severity": str(event.get("severity") or "info"),
                "evidence_ref": {
                    "kind": "event",
                    "ref": f"event:{event_id}",
                    "label": "Открыть событие",
                    "href": f"/agents/run/{run.id}?tab=evidence&view=events&evidence={event_id}",
                },
            }
        )
        if len(observation_items) >= 5:
            break

    is_active = bool(lifecycle.get("is_active"))
    action_status = "active" if is_active else "problem" if failed_activities else "completed"
    observation_status = "active" if is_active else "problem" if problem_events else "completed"
    conclusion_status = (
        "pending" if is_active else "problem" if outcome.get("status") in {"failed", "partial"} else "completed"
    )
    observation_summary = (
        _text(observation_items[0].get("summary") or observation_items[0].get("title"), limit=700)
        if observation_items
        else "Подтверждённых наблюдений пока нет."
    )
    action_summary = (
        f"Зафиксировано действий: {len(activities)}; ошибок: {len(failed_activities)}."
        if activities
        else "Исполняемые действия ещё не зафиксированы."
    )
    conclusion_summary = _text(outcome.get("reason") or outcome.get("label"), limit=700)
    return [
        {
            "id": "goal",
            "kind": "goal",
            "label": "Цель",
            "status": "completed" if activities or events or not is_active else "active",
            "count": 1,
            "important": 1,
            "problems": 0,
            "started_at": lifecycle.get("started_at"),
            "completed_at": lifecycle.get("started_at"),
            "summary": goal_text,
            "goal": goal_text,
        },
        {
            "id": "action",
            "kind": "action",
            "label": "Действия",
            "status": action_status,
            "count": len(activities),
            "important": len(failed_activities),
            "problems": len(failed_activities),
            "started_at": lifecycle.get("started_at"),
            "completed_at": lifecycle.get("completed_at"),
            "summary": action_summary,
            "action": action_summary,
        },
        {
            "id": "observation",
            "kind": "observation",
            "label": "Наблюдения",
            "status": observation_status,
            "count": len(findings) + len(important_events),
            "important": len(important_events),
            "problems": len(problem_events),
            "started_at": lifecycle.get("started_at"),
            "completed_at": lifecycle.get("completed_at"),
            "summary": observation_summary,
            "observation": observation_summary,
        },
        {
            "id": "conclusion",
            "kind": "conclusion",
            "label": "Вывод",
            "status": conclusion_status,
            "count": len(actions),
            "important": sum(1 for action in actions if action.get("priority") in {"P0", "P1"}),
            "problems": int(outcome.get("status") in {"failed", "partial"}),
            "started_at": lifecycle.get("completed_at"),
            "completed_at": lifecycle.get("completed_at"),
            "summary": conclusion_summary,
            "conclusion": conclusion_summary,
        },
    ]


def _activity_status(raw: Any, *, known_success: bool | None = None) -> tuple[str, bool | None]:
    if known_success is True:
        return "succeeded", True
    if known_success is False:
        return "failed", False
    value = str(raw or "").strip().lower()
    if value in {"done", "completed", "success", "succeeded"}:
        return "succeeded", True
    if value in {"failed", "error", "critical", "blocked"}:
        return "failed", False
    if value in {"running", "in_progress", "waiting", "pending"}:
        return value, None
    return "unknown", None


def build_agent_run_activity_items(run: AgentRun) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ordinal = 0
    for index, command in enumerate(run.commands_output or [], start=1):
        ordinal += 1
        raw_exit_code = command.get("exit_code")
        try:
            exit_code = int(raw_exit_code) if raw_exit_code is not None else None
        except (TypeError, ValueError):
            exit_code = None
        status, success = (
            _activity_status("", known_success=exit_code == 0) if exit_code is not None else ("unknown", None)
        )
        items.append(
            {
                "id": f"command-{index}",
                "ordinal": ordinal,
                "kind": "command",
                "status": status,
                "success": success,
                "title": _text(command.get("cmd") or f"Command {index}", limit=300),
                "summary": _text(command.get("stdout") or command.get("stderr"), limit=700),
                "tool": "shell",
                "task": "",
                "server": _text(run.server.name if run.server_id and run.server else "", limit=160),
                "command": _text(command.get("cmd"), limit=1_500),
                "exit_code": exit_code,
                "duration_ms": int(command.get("duration_ms") or 0),
                "started_at": command.get("timestamp"),
                "completed_at": command.get("timestamp"),
                "error": _text(command.get("stderr") if exit_code not in {None, 0} else "", limit=700),
                "evidence_refs": [],
            }
        )
    for index, task in enumerate(run.plan_tasks or [], start=1):
        ordinal += 1
        status, success = _activity_status(task.get("status"))
        items.append(
            {
                "id": f"step-{task.get('id') or index}",
                "ordinal": ordinal,
                "kind": "step",
                "status": status,
                "success": success,
                "title": _text(task.get("name") or f"Task {index}", limit=300),
                "summary": _text(task.get("result") or task.get("thought") or task.get("description"), limit=700),
                "tool": _text(task.get("action"), limit=120),
                "task": _text(task.get("name") or task.get("id"), limit=200),
                "server": "",
                "command": _text(task.get("action"), limit=1_500),
                "exit_code": task.get("exit_code"),
                "duration_ms": 0,
                "started_at": task.get("started_at"),
                "completed_at": task.get("completed_at"),
                "error": _text(task.get("error"), limit=700),
                "evidence_refs": [],
            }
        )
    for index, iteration in enumerate(run.iterations_log or [], start=1):
        ordinal += 1
        items.append(
            {
                "id": f"iteration-{iteration.get('iteration') or index}",
                "ordinal": ordinal,
                "kind": "iteration",
                "status": "unknown",
                "success": None,
                "title": _text(iteration.get("action") or f"Iteration {index}", limit=300),
                "summary": _text(iteration.get("observation") or iteration.get("thought"), limit=700),
                "tool": _text(iteration.get("action"), limit=120),
                "task": _text(iteration.get("task") or iteration.get("task_id"), limit=200),
                "server": _text(
                    (iteration.get("args") or {}).get("server") if isinstance(iteration.get("args"), dict) else "",
                    limit=160,
                ),
                "command": _text(
                    (iteration.get("args") or {}).get("command") if isinstance(iteration.get("args"), dict) else "",
                    limit=1_500,
                ),
                "exit_code": None,
                "duration_ms": int(iteration.get("duration_ms") or 0),
                "started_at": iteration.get("timestamp"),
                "completed_at": iteration.get("timestamp"),
                "error": "",
                "evidence_refs": [],
            }
        )
    for index, tool_call in enumerate(run.tool_calls or [], start=1):
        ordinal += 1
        explicit_success = tool_call.get("success") if isinstance(tool_call.get("success"), bool) else None
        raw_exit_code = tool_call.get("exit_code")
        try:
            exit_code = int(raw_exit_code) if raw_exit_code is not None else None
        except (TypeError, ValueError):
            exit_code = None
        known_success = (
            explicit_success if explicit_success is not None else (exit_code == 0 if exit_code is not None else None)
        )
        status, success = _activity_status(tool_call.get("status"), known_success=known_success)
        args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
        items.append(
            {
                "id": f"tool-{index}",
                "ordinal": ordinal,
                "kind": "tool",
                "status": status,
                "success": success,
                "title": _text(tool_call.get("tool") or f"Tool {index}", limit=300),
                "summary": _text(tool_call.get("result_preview") or tool_call.get("result"), limit=700),
                "tool": _text(tool_call.get("tool"), limit=120),
                "task": _text(tool_call.get("task") or tool_call.get("task_id"), limit=200),
                "server": _text(tool_call.get("server") or args.get("server"), limit=160),
                "command": _text(args.get("command"), limit=1_500),
                "exit_code": exit_code,
                "duration_ms": int(tool_call.get("duration_ms") or 0),
                "started_at": tool_call.get("timestamp"),
                "completed_at": tool_call.get("timestamp"),
                "error": _text(tool_call.get("error"), limit=700),
                "evidence_refs": [],
            }
        )
    for item in items:
        item["evidence_refs"] = [_activity_ref(run.id, item)]
    return items


def _activity_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "activities_total": len(items),
        "activities_succeeded": sum(1 for item in items if item.get("status") == "succeeded"),
        "activities_failed": sum(1 for item in items if item.get("status") == "failed"),
        "activities_unknown": sum(
            1 for item in items if item.get("status") in {"unknown", "recorded"} or item.get("success") is None
        ),
    }


def _operation_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    operations = [item for item in items if item.get("kind") in {"command", "step", "tool"}]
    return {
        "operations_total": len(operations),
        "operations_succeeded": sum(1 for item in operations if item.get("status") == "succeeded"),
        "operations_failed": sum(1 for item in operations if item.get("status") == "failed"),
        "operations_unknown": sum(1 for item in operations if item.get("status") == "unknown"),
        "commands": sum(1 for item in operations if item.get("kind") == "command"),
        "steps": sum(1 for item in operations if item.get("kind") == "step"),
        "tool_calls": sum(1 for item in operations if item.get("kind") == "tool"),
        "iterations": len([item for item in items if item.get("kind") == "iteration"]),
    }


def _delivery_for_run(run: AgentRun, events: list[dict[str, Any]], report_ready: bool) -> dict[str, Any]:
    configured_delivery = normalize_report_delivery(run.agent.report_delivery if run.agent_id and run.agent else {})
    telegram = configured_delivery.get("telegram") or {}
    enabled = bool(telegram.get("enabled"))
    notification_config = load_notification_config()
    bot_token_present = bool(str(notification_config.get("telegram_bot_token") or "").strip())
    configured_chat_id = str(telegram.get("chat_id") or notification_config.get("telegram_chat_id") or "").strip()
    configured = bool(enabled and bot_token_present and configured_chat_id)
    delivery_events = [event for event in events if event.get("event_type") in DELIVERY_EVENT_TYPES]
    latest = delivery_events[-1] if delivery_events else None
    event_type = str((latest or {}).get("event_type") or "")
    payload = (latest or {}).get("payload") if isinstance((latest or {}).get("payload"), dict) else {}
    historical_config_block = bool(
        event_type == "agent_report_delivery_skipped"
        and str(payload.get("reason") or "").strip().lower() == "telegram_not_configured"
    )
    if historical_config_block:
        configured = False
    status = "disabled"
    severity = "info"
    label = "Выключена"
    description = "Внешняя доставка выключена."
    if enabled and not configured:
        status, severity, label = "blocked", "warning", "Требуется настройка"
        description = "Для Telegram не настроены bot token или chat id."
    elif enabled and not report_ready:
        status, label, description = "waiting_report", "Ждёт отчёт", "Доставка начнётся после формирования отчёта."
    elif event_type == "agent_report_delivery_accepted":
        status, severity, label = "in_progress", "info", "В очереди"
        description = "Доставка отчёта принята worker-очередью."
    elif event_type in {"agent_report_delivered", "agent_report_delivery_sent"}:
        status, severity, label = "sent", "success", "Доставлено"
        description = str((latest or {}).get("summary") or "Отчёт доставлен.")
    elif event_type == "agent_report_delivery_failed":
        status, severity, label = "failed", "critical", "Ошибка"
        description = str((latest or {}).get("summary") or "Доставка завершилась ошибкой.")
    elif event_type == "agent_report_delivery_skipped":
        status, severity, label = "blocked", "warning", "Требуется настройка"
        description = str((latest or {}).get("summary") or description)
    elif enabled and configured and report_ready:
        status, severity, label = "pending", "warning", "Ожидает"
        description = "Отчёт готов, подтверждения доставки ещё нет."

    delivery_in_progress = event_type == "agent_report_delivery_accepted"
    can_retry = bool(enabled and configured and report_ready and status != "sent" and not delivery_in_progress)
    blocked_reason = ""
    if not enabled:
        blocked_reason = "delivery_disabled"
    elif not configured:
        blocked_reason = "telegram_not_configured"
    elif not report_ready:
        blocked_reason = "report_not_ready"
    elif status == "sent":
        blocked_reason = "already_sent"
    elif delivery_in_progress:
        blocked_reason = "delivery_in_progress"
    attempt_ids = {
        str(event.get("payload", {}).get("attempt_id") or "")
        for event in delivery_events
        if isinstance(event.get("payload"), dict) and event.get("payload", {}).get("attempt_id")
    }
    unkeyed_attempts = sum(
        1
        for event in delivery_events
        if event.get("event_type") != "agent_report_delivery_accepted"
        and not str((event.get("payload") or {}).get("attempt_id") or "")
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "channel": "telegram" if enabled else "",
        "target": _mask_identifier(configured_chat_id) if configured else "",
        "status": status,
        "label": label,
        "severity": severity,
        "description": _text(description, limit=700),
        "summary": _text(description, limit=700),
        "can_retry": can_retry,
        "blocked_reason": blocked_reason,
        "setup_url": "/settings/notifications",
        "attempt_id": _text(payload.get("attempt_id"), limit=80),
        "attempt_count": len(attempt_ids) + unkeyed_attempts,
        "last_attempt_at": (latest or {}).get("created_at"),
        "next_action": "Повторить доставку" if can_retry else "Настроить Telegram" if not configured else "",
    }


def _report_generation(run: AgentRun, document: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    stored_outcome = run.execution_outcome if isinstance(run.execution_outcome, dict) else {}
    stored = stored_outcome.get("report_generation")
    stored = stored if isinstance(stored, dict) else {}
    if document["available"] and outcome.get("exit_reason") == "llm_error":
        status, label, severity = "ready_with_fallback", "Отчёт готов по сохранённым данным", "warning"
        error = _text((outcome.get("details") or {}).get("technical_reason") or "LLM call failed", limit=700)
    elif stored.get("status") in {"generating", "ready", "ready_with_fallback", "failed"}:
        status = str(stored["status"])
        label = (
            _text(stored.get("label"), limit=200)
            or {
                "generating": "Отчёт формируется",
                "ready": "Отчёт готов",
                "ready_with_fallback": "Отчёт готов по сохранённым данным",
                "failed": "Отчёт не сформирован",
            }[status]
        )
        severity = str(
            stored.get("severity")
            or ("success" if status == "ready" else "warning" if status != "failed" else "critical")
        )
        error = _text(stored.get("error"), limit=700)
    elif document["available"]:
        status, label, severity, error = "ready", "Отчёт готов", "success", ""
    elif run.status in TERMINAL_STATUSES:
        status, label, severity = "failed", "Отчёт не сформирован", "critical"
        error = _text(run.ai_analysis, limit=700)
    else:
        status, label, severity, error = "generating", "Отчёт формируется", "info", ""
    return {
        "status": status,
        "label": label,
        "ready": status in {"ready", "ready_with_fallback"},
        "severity": severity,
        "error": error,
        "generated_at": (
            _text(stored.get("generated_at"), limit=80)
            or (
                run.completed_at.isoformat()
                if status in {"ready", "ready_with_fallback"} and run.completed_at
                else None
            )
        ),
    }


def _evidence_state(
    run: AgentRun, outcome: dict[str, Any], coverage: dict[str, Any], activities: list[dict[str, Any]]
) -> dict[str, Any]:
    checked, total = coverage.get("checked"), coverage.get("total")
    if run.status not in TERMINAL_STATUSES:
        status, label = "pending", "Сбор доказательств продолжается"
    elif total and checked is not None and checked < total:
        status, label = "partial", "Охват неполный"
    elif not activities:
        status, label = "insufficient", "Недостаточно доказательств"
    elif outcome.get("status") == "success":
        status, label = "complete", "Доказательства собраны"
    else:
        status, label = "partial", "Доказательства собраны частично"
    summary = label
    if total and checked is not None:
        summary = f"Проверено {checked} из {total} {coverage.get('unit') or 'объектов'}."
    return {"status": status, "label": label, "summary": summary, "coverage": coverage}


def _revision(run: AgentRun, outcome: dict[str, Any], document: dict[str, Any], watermark: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "run_id": run.id,
            "status": run.status,
            "outcome": outcome.get("status"),
            "outcome_reason": outcome.get("reason"),
            "document": document.get("checksum_sha256"),
            "watermark": watermark,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"r2-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def build_agent_run_report_v2(run: AgentRun) -> dict[str, Any]:
    document_content = redacted_full_document(run)
    document = _document_metadata(run)
    lifecycle = _lifecycle(run)
    coverage = _coverage(document_content)
    outcome = _outcome_for_run(run, document_content, coverage)
    events = _all_public_events(run)
    event_counts = _event_counts(events)
    activities = build_agent_run_activity_items(run)
    activity_counts = _activity_counts(activities)
    operation_counts = _operation_counts(activities)
    evidence_registry = _evidence_registry(
        run,
        events,
        activities,
        document_available=document["available"],
    )
    findings, actions = _atomic_findings_and_actions(run, document_content, evidence_registry)
    findings.sort(key=lambda item: -_severity_rank(item.get("severity")))
    evidence_state = _evidence_state(run, outcome, coverage, activities)
    report_generation = _report_generation(run, document, outcome)
    delivery = _delivery_for_run(run, events, report_generation["ready"])
    phases = _phase_summary(run, events, activities, findings, actions, lifecycle, outcome)
    watermark = {
        "sequence_no": max((int(event.get("sequence_no") or 0) for event in events), default=0),
        "total": len(events),
        "updated_at": events[-1].get("created_at") if events else None,
    }
    findings_count = sum(1 for finding in findings if finding.get("kind") == "finding")
    risks_count = sum(1 for finding in findings if finding.get("kind") == "risk")
    counts = {
        **event_counts,
        "findings": findings_count,
        "risks": risks_count,
        "actions": len(actions),
        **activity_counts,
        **operation_counts,
        "artifacts": AgentRunArtifact.objects.filter(run=run).count(),
    }
    coverage_value = (
        f"{coverage['checked']}/{coverage['total']}"
        if coverage.get("checked") is not None and coverage.get("total")
        else "—"
    )
    report_delivery_tone = (
        report_generation["severity"]
        if _severity_rank(report_generation["severity"]) >= _severity_rank(delivery["severity"])
        else delivery["severity"]
    )
    mandatory_indicators = [
        {
            "id": "outcome",
            "role": "primary",
            "label": "Результат",
            "value": outcome["label"],
            "value_kind": "status",
            "unit": "",
            "numerator": None,
            "denominator": None,
            "tone": outcome["severity"],
            "priority": 1,
            "evidence_refs": [],
        },
        {
            "id": "report_delivery",
            "role": "primary",
            "label": "Отчёт и доставка",
            "value": f"{report_generation['label']} · {delivery['label']}",
            "value_kind": "status",
            "unit": "",
            "numerator": None,
            "denominator": None,
            "tone": report_delivery_tone,
            "priority": 2,
            "evidence_refs": [_document_ref(run.id, "document", 1, "Открыть отчёт")] if document["available"] else [],
        },
    ]
    fallback_indicators = [
        {
            "id": "coverage",
            "role": "primary",
            "label": "Охват",
            "value": coverage_value,
            "value_kind": "ratio",
            "unit": coverage.get("unit") or "objects",
            "numerator": coverage.get("checked"),
            "denominator": coverage.get("total"),
            "tone": "warning" if evidence_state["status"] in {"partial", "insufficient"} else "success",
            "priority": 20,
            "evidence_refs": [_document_ref(run.id, "summary", 1, "Источник охвата")] if document["available"] else [],
        },
        {
            "id": "operations",
            "role": "supporting",
            "label": "Операции",
            "value": str(operation_counts["operations_total"]),
            "value_kind": "count",
            "unit": "операций",
            "numerator": operation_counts["operations_total"],
            "denominator": None,
            "tone": "info",
            "priority": 25,
            "evidence_refs": [
                _activity_ref(run.id, item) for item in activities if item.get("kind") in {"command", "step", "tool"}
            ][:3],
        },
        {
            "id": "problems",
            "role": "primary",
            "label": "Проблемы",
            "value": str(event_counts["execution_problem_events"] + risks_count),
            "value_kind": "count",
            "unit": "проблем",
            "numerator": event_counts["execution_problem_events"] + risks_count,
            "denominator": None,
            "tone": "high" if event_counts["execution_problem_events"] + risks_count else "success",
            "priority": 30,
            "evidence_refs": [
                evidence_registry[f"event:{event['id']}"]
                for event in events
                if _severity_rank(event.get("severity")) >= _severity_rank("warning")
                and f"event:{event['id']}" in evidence_registry
            ][:3],
        },
        {
            "id": "duration",
            "role": "supporting",
            "label": "Длительность",
            "value": lifecycle["duration_label"],
            "value_kind": "duration",
            "unit": "ms",
            "numerator": lifecycle["duration_ms"],
            "denominator": None,
            "tone": "info",
            "priority": 40,
            "evidence_refs": [],
        },
    ]
    model_indicators = sorted(
        _validated_model_indicators(run, evidence_registry, document_available=document["available"]),
        key=lambda item: (int(item.get("priority") or 100), str(item.get("id") or "")),
    )
    indicators = list(mandatory_indicators)
    seen_indicator_ids = {str(item["id"]) for item in indicators}
    for indicator in [*model_indicators, *fallback_indicators]:
        indicator_id = str(indicator.get("id") or "")
        if not indicator_id or indicator_id in seen_indicator_ids:
            continue
        indicators.append(indicator)
        seen_indicator_ids.add(indicator_id)
        if len(indicators) >= 8:
            break
    report_revision = _revision(run, outcome, document, watermark)
    updated_at = watermark.get("updated_at") or lifecycle.get("completed_at") or lifecycle.get("started_at")
    return {
        "success": True,
        "code": "ok",
        "data": None,
        "schema_version": REPORT_V2_SCHEMA_VERSION,
        "run": {
            "id": run.id,
            "agent_id": run.agent_id,
            "agent_name": _text(run.agent.name if run.agent_id and run.agent else "Agent", limit=200),
            "agent_type": run.agent.agent_type if run.agent_id and run.agent else "custom",
            "agent_mode": run.agent.mode if run.agent_id and run.agent else "mini",
            "goal": _text((run.agent.goal or run.agent.ai_prompt) if run.agent_id and run.agent else "", limit=1_200),
            "server_id": run.server_id,
            "server_name": _text(run.server.name if run.server_id and run.server else "—", limit=200),
        },
        "lifecycle": lifecycle,
        "outcome": outcome,
        "evidence_state": evidence_state,
        "report_generation": report_generation,
        "delivery": delivery,
        "indicators": indicators,
        "findings": findings,
        "actions": actions,
        "phases": phases,
        "counts": counts,
        "report_revision": report_revision,
        "event_high_watermark": watermark,
        "updated_at": updated_at,
        "document": document,
        "evidence_links": {
            "events": f"/servers/api/agents/runs/{run.id}/events/",
            "activity": f"/servers/api/agents/runs/{run.id}/activity/",
            "artifacts": f"/servers/api/agents/runs/{run.id}/artifacts/",
            "artifacts_zip": f"/servers/api/agents/runs/{run.id}/artifacts/download-all/",
            "document": document.get("detail_url") or "",
            "audit_export": f"/servers/api/agents/runs/{run.id}/audit-export/",
        },
    }


def _split_filter(value: str | None) -> set[str]:
    return {part.strip().lower() for part in str(value or "").split(",") if part.strip()}


def _parse_bool_filter(value: str | None) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def build_agent_run_events_v2(
    run: AgentRun,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str = "",
    direction: str = "older",
    severity: str = "",
    phase: str = "",
    category: str = "",
    event_type: str = "",
    important: str = "",
    query: str = "",
) -> dict[str, Any]:
    items = _all_public_events(run)
    severity_filter = _split_filter(severity)
    phase_filter = _split_filter(phase)
    category_filter = _split_filter(category)
    event_type_filter = _split_filter(event_type)
    important_filter = _parse_bool_filter(important)
    query_lower = str(query or "").strip().lower()
    filtered = []
    for item in items:
        if severity_filter and str(item.get("severity") or "").lower() not in severity_filter:
            continue
        if phase_filter and str(item.get("phase") or "").lower() not in phase_filter:
            continue
        if category_filter and str(item.get("category") or "").lower() not in category_filter:
            continue
        if event_type_filter and str(item.get("event_type") or "").lower() not in event_type_filter:
            continue
        if important_filter is not None and bool(item.get("important")) is not important_filter:
            continue
        if query_lower:
            haystack = " ".join(
                str(item.get(key) or "") for key in ("event_type", "title", "summary", "message", "source")
            ).lower()
            if query_lower not in haystack:
                continue
        filtered.append(item)

    page_limit = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    normalized_direction = "newer" if str(direction).lower() == "newer" else "older"
    try:
        cursor_sequence = int(cursor) if cursor else None
    except (TypeError, ValueError):
        cursor_sequence = None
    if normalized_direction == "older":
        candidates = [
            item for item in filtered if cursor_sequence is None or int(item.get("sequence_no") or 0) < cursor_sequence
        ]
        selected_desc = list(reversed(candidates))[: page_limit + 1]
        has_more = len(selected_desc) > page_limit
        selected = list(reversed(selected_desc[:page_limit]))
        next_cursor = str(selected[0]["sequence_no"]) if selected and has_more else None
        prev_cursor = str(selected[-1]["sequence_no"]) if selected else None
    else:
        candidates = [
            item for item in filtered if cursor_sequence is None or int(item.get("sequence_no") or 0) > cursor_sequence
        ]
        selected = candidates[: page_limit + 1]
        has_more = len(selected) > page_limit
        selected = selected[:page_limit]
        next_cursor = str(selected[-1]["sequence_no"]) if selected and has_more else None
        prev_cursor = str(selected[0]["sequence_no"]) if selected else None
    watermark = {
        "sequence_no": max((int(item.get("sequence_no") or 0) for item in items), default=0),
        "total": len(items),
        "updated_at": items[-1].get("created_at") if items else None,
    }
    return {
        "success": True,
        "items": selected,
        "events": selected,
        "page": {
            "limit": page_limit,
            "direction": normalized_direction,
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
            "has_more": has_more,
            "returned": len(selected),
            "truncated": has_more,
        },
        "total": len(filtered),
        "filters": {
            "severity": sorted(severity_filter),
            "phase": sorted(phase_filter),
            "category": sorted(category_filter),
            "event_type": sorted(event_type_filter),
            "important": important_filter,
            "q": query_lower,
        },
        "event_high_watermark": watermark,
        "event_watermark": watermark,
        "updated_at": watermark.get("updated_at"),
        "integrity": verify_agent_audit_chain(run.id),
    }


def _encode_activity_cursor(ordinal: int) -> str:
    return base64.urlsafe_b64encode(f"activity:{int(ordinal)}".encode()).decode().rstrip("=")


def _decode_activity_cursor(value: str) -> int | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        prefix, raw = decoded.split(":", 1)
        return int(raw) if prefix == "activity" else None
    except (ValueError, UnicodeDecodeError):
        return None


def build_agent_run_activity_response(
    run: AgentRun,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str = "",
    direction: str = "older",
    kind: str = "",
    status: str = "",
) -> dict[str, Any]:
    items = build_agent_run_activity_items(run)
    kind_filter = _split_filter(kind)
    status_filter = _split_filter(status)
    filtered = [
        item
        for item in items
        if (not kind_filter or str(item.get("kind") or "").lower() in kind_filter)
        and (not status_filter or str(item.get("status") or "").lower() in status_filter)
    ]
    page_limit = max(1, min(int(limit or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    normalized_direction = "newer" if str(direction).lower() == "newer" else "older"
    cursor_ordinal = _decode_activity_cursor(cursor)
    if normalized_direction == "older":
        candidates = [item for item in filtered if cursor_ordinal is None or int(item["ordinal"]) < cursor_ordinal]
        selected_desc = list(reversed(candidates))[: page_limit + 1]
        has_more = len(selected_desc) > page_limit
        selected = list(reversed(selected_desc[:page_limit]))
        next_cursor = _encode_activity_cursor(selected[0]["ordinal"]) if selected and has_more else None
        prev_cursor = _encode_activity_cursor(selected[-1]["ordinal"]) if selected else None
    else:
        candidates = [item for item in filtered if cursor_ordinal is None or int(item["ordinal"]) > cursor_ordinal]
        selected = candidates[: page_limit + 1]
        has_more = len(selected) > page_limit
        selected = selected[:page_limit]
        next_cursor = _encode_activity_cursor(selected[-1]["ordinal"]) if selected and has_more else None
        prev_cursor = _encode_activity_cursor(selected[0]["ordinal"]) if selected else None
    return {
        "success": True,
        "items": selected,
        "page": {
            "limit": page_limit,
            "direction": normalized_direction,
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
            "has_more": has_more,
            "returned": len(selected),
            "truncated": has_more,
        },
        "total": len(filtered),
        "counts": _activity_counts(filtered),
        "filters": {"kind": sorted(kind_filter), "status": sorted(status_filter)},
        "updated_at": run.completed_at.isoformat() if run.completed_at else run.started_at.isoformat(),
    }


def build_agent_run_artifacts_response(run: AgentRun) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for artifact in AgentRunArtifact.objects.filter(run=run).order_by("name", "id"):
        content = str(artifact.content or "")
        encoded = content.encode("utf-8", errors="replace")
        size_bytes = int(artifact.size_bytes or len(encoded))
        items.append(
            {
                "id": artifact.id,
                "key": _text(artifact.artifact_key, limit=80),
                "name": _text(artifact.name, limit=255),
                "type": _text(artifact.artifact_type, limit=40),
                "description": _text(artifact.description, limit=500),
                "content_type": _text(artifact.content_type, limit=120),
                "size_bytes": size_bytes,
                "size_label": _bytes_label(size_bytes),
                "checksum_sha256": hashlib.sha256(encoded).hexdigest(),
                "truncated": bool(artifact.truncated),
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
                "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
                "download_url": f"/servers/api/agents/runs/{run.id}/artifacts/{artifact.id}/download/",
            }
        )
    return {
        "success": True,
        "items": items,
        "total": len(items),
        "download_all_url": f"/servers/api/agents/runs/{run.id}/artifacts/download-all/" if items else "",
    }


__all__ = [
    "REPORT_V2_SCHEMA_VERSION",
    "build_agent_run_activity_response",
    "build_agent_run_artifacts_response",
    "build_agent_run_events_v2",
    "build_agent_run_report_v2",
    "redacted_full_document",
]
