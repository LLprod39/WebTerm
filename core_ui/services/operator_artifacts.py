"""Chat artifacts for Operator workbench (ansible/scripts/reports)."""

from __future__ import annotations

import re
from typing import Any

from core_ui.models import ChatArtifact, ChatMessage, ChatSession

# Role-invention / fleet dump prose the model loves to write instead of using the UI card.
_INVENTORY_DUMP_MARKERS = re.compile(
    r"(?:"
    r"API\s*шлюз|"
    r"SSH\s*прокси|"
    r"CI/?CD|"
    r"staging\s+окружен|"
    r"веб\s+фронт|"
    r"тестов(ая|ая\s+сред)|"
    r"•\s*[\w.-]+(?:\s*,\s*[\w.-]+)+\s*[—–-]|"  # • a, b — role
    r"(?:^|\n)\s*[•\-\*]\s*(?:api|web|db|stg|ci|prom|redis|grafana|bastion|lunix)"
    r")",
    re.I | re.M,
)
_HOSTISH_BULLETS = re.compile(
    r"(?:^|\n)\s*(?:[•\-\*]|\d+\.)\s*.{0,40}(?:prod|stg|runner|primary|replica|grafana|lunix|bastion)",
    re.I,
)


def serialize_artifact(artifact: ChatArtifact) -> dict[str, Any]:
    return {
        "id": artifact.pk,
        "session_id": artifact.session_id,
        "message_id": artifact.message_id,
        "kind": artifact.kind,
        "title": artifact.title,
        "content": artifact.content,
        "version": artifact.version,
        "metadata": artifact.metadata or {},
        "saved_playbook_id": artifact.saved_playbook_id,
        "created_at": artifact.created_at.isoformat(),
        "updated_at": artifact.updated_at.isoformat(),
    }


def looks_like_inventory_prose_dump(content: str) -> bool:
    """True when the model listed fleet hosts/roles in text (UI card should own that)."""
    text = str(content or "").strip()
    if len(text) < 80:
        return False
    if _INVENTORY_DUMP_MARKERS.search(text):
        return True
    bullets = _HOSTISH_BULLETS.findall(text)
    if len(bullets) >= 3:
        return True
    # Many comma-separated host names on one line
    if len(re.findall(r"\b[\w-]+-(?:prod|stg|01|02)\b", text, flags=re.I)) >= 5:
        return True
    return False


def short_inventory_line(*, count: int, status_counts: dict[str, Any] | None = None) -> str:
    sc = status_counts if isinstance(status_counts, dict) else {}
    healthy = int(sc.get("healthy") or 0)
    warning = int(sc.get("warning") or 0)
    critical = int(sc.get("critical") or 0)
    unreachable = int(sc.get("unreachable") or 0)
    unknown = int(sc.get("unknown") or 0)
    if count <= 0:
        count = healthy + warning + critical + unreachable + unknown
    parts = [f"{count} серверов"]
    if healthy and healthy == count:
        parts.append("все healthy")
    else:
        bits = []
        if healthy:
            bits.append(f"{healthy} ok")
        if warning:
            bits.append(f"{warning} warning")
        if critical:
            bits.append(f"{critical} critical")
        if unreachable:
            bits.append(f"{unreachable} unreachable")
        if unknown:
            bits.append(f"{unknown} unknown")
        if bits:
            parts.append(" · ".join(bits))
    return " · ".join(parts) + "."


def compress_inventory_assistant_content(message: ChatMessage) -> bool:
    """If inventory UI card is present and prose is a host dump, replace with one line.

    Returns True when content was rewritten. Platform-enforced so the model cannot
    spam role descriptions even if it ignores the system prompt.
    """
    if not message:
        return False
    meta = message.metadata if isinstance(message.metadata, dict) else {}
    tables = meta.get("tables") if isinstance(meta.get("tables"), list) else []
    servers_table = next(
        (t for t in tables if isinstance(t, dict) and t.get("kind") == "servers"),
        None,
    )
    if not servers_table and not meta.get("inventory_card"):
        return False
    content = message.content or ""
    host_tokens = len(re.findall(r"\b[\w-]+-\d{2}\b", content))
    if not looks_like_inventory_prose_dump(content) and host_tokens < 4:
        return False

    count = 0
    status_counts: dict[str, Any] | None = None
    if isinstance(servers_table, dict):
        status_counts = servers_table.get("status_counts") if isinstance(servers_table.get("status_counts"), dict) else None
        items = servers_table.get("items") if isinstance(servers_table.get("items"), list) else []
        count = len(items) or int(meta.get("inventory_count") or 0)
        title = str(servers_table.get("title") or "")
        m = re.search(r"(\d+)", title)
        if m and not count:
            count = int(m.group(1))
    if not count:
        count = int(meta.get("inventory_count") or 0)
    if not status_counts and isinstance(meta.get("inventory_status_counts"), dict):
        status_counts = meta["inventory_status_counts"]

    short = short_inventory_line(count=count, status_counts=status_counts)
    if (content or "").strip() == short:
        return False
    message.content = short
    message.metadata = {**meta, "inventory_prose_compressed": True}
    message.save(update_fields=["content", "metadata"])
    return True


def list_artifacts(session: ChatSession) -> list[dict[str, Any]]:
    rows = session.artifacts.order_by("-updated_at", "-id")[:50]
    return [serialize_artifact(a) for a in rows]


def create_artifact(
    *,
    session: ChatSession,
    kind: str,
    title: str,
    content: str,
    message: ChatMessage | None = None,
    metadata: dict | None = None,
) -> ChatArtifact:
    kind_norm = str(kind or ChatArtifact.KIND_OTHER).strip().lower()
    allowed = {c[0] for c in ChatArtifact.KIND_CHOICES}
    if kind_norm not in allowed:
        kind_norm = ChatArtifact.KIND_OTHER
    return ChatArtifact.objects.create(
        session=session,
        message=message,
        kind=kind_norm,
        title=(title or "Artifact")[:200],
        content=content or "",
        version=1,
        metadata=metadata or {},
    )


def update_artifact_content(
    artifact: ChatArtifact,
    *,
    content: str,
    title: str | None = None,
    bump_version: bool = True,
) -> ChatArtifact:
    artifact.content = content or ""
    if title is not None:
        artifact.title = title[:200]
    if bump_version:
        artifact.version = int(artifact.version or 1) + 1
    fields = ["content", "updated_at"]
    if title is not None:
        fields.append("title")
    if bump_version:
        fields.append("version")
    artifact.save(update_fields=fields)
    return artifact


def get_artifact_for_user(user, artifact_id: int) -> ChatArtifact | None:
    return (
        ChatArtifact.objects.select_related("session")
        .filter(pk=artifact_id, session__user=user)
        .first()
    )


def extract_artifacts_from_tool_result(
    *,
    session: ChatSession,
    message: ChatMessage | None,
    action_type: str,
    result: dict[str, Any],
) -> list[ChatArtifact]:
    """Best-effort: persist yaml/scripts from tool results as artifacts."""
    created: list[ChatArtifact] = []
    if not isinstance(result, dict):
        return created
    # Nested result from execute_tool wrap
    payload = result.get("result") if isinstance(result.get("result"), dict) else result

    yaml_text = str(payload.get("yaml") or payload.get("source_yaml") or "").strip()
    if yaml_text and ("playbook" in action_type or "ansible" in action_type or yaml_text.startswith("---")):
        created.append(
            create_artifact(
                session=session,
                kind=ChatArtifact.KIND_ANSIBLE,
                title=str(payload.get("name") or payload.get("title") or "Ansible playbook")[:200],
                content=yaml_text,
                message=message,
                metadata={"source_action": action_type},
            )
        )

    script = str(payload.get("script") or "").strip()
    if script:
        created.append(
            create_artifact(
                session=session,
                kind=ChatArtifact.KIND_SCRIPT,
                title=str(payload.get("title") or "Script")[:200],
                content=script,
                message=message,
                metadata={"source_action": action_type},
            )
        )

    # create_playbook returns playbook without yaml in body sometimes
    pb = payload.get("playbook") if isinstance(payload.get("playbook"), dict) else None
    if pb and pb.get("id") and not created:
        created.append(
            create_artifact(
                session=session,
                kind=ChatArtifact.KIND_ANSIBLE if pb.get("kind") == "ansible" else ChatArtifact.KIND_OTHER,
                title=str(pb.get("name") or f"Playbook #{pb['id']}")[:200],
                content=f"# playbook_id={pb['id']}\n# Open in Playbooks UI to edit\n",
                message=message,
                metadata={"playbook_id": pb["id"], "source_action": action_type},
            )
        )
        if created:
            created[-1].saved_playbook_id = int(pb["id"])
            created[-1].save(update_fields=["saved_playbook_id", "updated_at"])

    return created


def maybe_attach_chart_metadata(message: ChatMessage, tool_result: dict[str, Any]) -> None:
    """If tool returned metric series, attach chart metadata to the assistant message."""
    if not message or not isinstance(tool_result, dict):
        return
    payload = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else tool_result
    if not isinstance(payload, dict):
        return

    # Point-in-time snapshot from operator.server_metrics → nice card, not terminal dock
    if (
        payload.get("cpu_percent") is not None
        or payload.get("mem_percent") is not None
        or payload.get("disk_mounts")
        or payload.get("ui_metrics")
    ) and payload.get("server_id") is not None and "servers" not in payload:
        meta = dict(message.metadata or {})
        meta["metrics"] = {
            "server_id": payload.get("server_id"),
            "name": payload.get("name") or "",
            "host": payload.get("host") or "",
            "status": payload.get("status") or "unknown",
            "cpu_percent": payload.get("cpu_percent"),
            "mem_percent": payload.get("mem_percent"),
            "disk_percent": payload.get("disk_percent"),
            "disk_mounts": payload.get("disk_mounts") if isinstance(payload.get("disk_mounts"), list) else [],
            "collected_at": payload.get("collected_at"),
            # Short UI note only — never dump English model-facing status_note into the card.
            "note": payload.get("ui_note") or None,
        }
        message.metadata = meta
        message.save(update_fields=["metadata"])

    series = payload.get("series") or payload.get("points")
    if not isinstance(series, list) or len(series) < 2:
        return
    meta = dict(message.metadata or {})
    meta["chart"] = {
        "title": payload.get("title") or payload.get("metric_key") or "Metric",
        "series": series[:200],
        "unit": payload.get("unit") or "",
        "server_id": payload.get("server_id"),
    }
    message.metadata = meta
    message.save(update_fields=["metadata"])


def maybe_attach_table_metadata(message: ChatMessage, tool_result: dict[str, Any], *, action_type: str = "") -> None:
    """Attach structured tables for known tool payloads (servers, alerts, …).

    Inventory cards are opt-in only: attach when payload.ui_table is True.
    Lookup / connect / resolve_server must never spam the full «Серверы · N» card.
    """
    if not message or not isinstance(tool_result, dict):
        return
    payload = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else tool_result
    if not isinstance(payload, dict):
        return

    table: dict[str, Any] | None = None

    # Explicit suppress (lookup / resolve / connect)
    ui_table = payload.get("ui_table")
    if ui_table is False:
        servers = None
    else:
        servers = payload.get("servers")
    # Servers inventory card: only when tool asks for it (show_in_chat / ui_table=true).
    # Missing ui_table on a servers list still attaches for backwards compat, except known lookup tools.
    if (
        isinstance(servers, list)
        and servers
        and isinstance(servers[0], dict)
        and (
            ui_table is True
            or (
                ui_table is not False
                and action_type
                not in {
                    "operator.list_servers",
                    "operator.resolve_server",
                    "operator.server_info",
                }
            )
        )
    ):
        headers = ["ID", "Имя", "Host", "Порт", "Теги", "AI RO"]
        rows = []
        items = []
        for s in servers[:80]:
            tags = s.get("tags")
            if isinstance(tags, list):
                tags_list = [str(t) for t in tags[:6]]
                tags_s = ", ".join(tags_list) or "—"
            else:
                tags_list = [part.strip() for part in str(tags or "").split(",") if part.strip()]
                tags_s = ", ".join(tags_list) or "—"
            rows.append(
                [
                    s.get("id", ""),
                    s.get("name", ""),
                    s.get("host", ""),
                    s.get("port", ""),
                    tags_s,
                    "yes" if s.get("ai_read_only") else "no",
                ]
            )
            items.append(
                {
                    "id": s.get("id"),
                    "name": s.get("name") or "",
                    "host": s.get("host") or "",
                    "port": s.get("port") or 22,
                    "tags": tags_list,
                    "ai_read_only": bool(s.get("ai_read_only")),
                    "os_family": s.get("os_family") or "",
                    "status": s.get("status") or "",
                    "terminal_url": f"/servers/{s.get('id')}/terminal",
                    "detail_url": "/servers",
                }
            )
        table = {
            "title": f"Серверы · {payload.get('count', len(rows))}",
            "headers": headers,
            "rows": rows,
            "kind": "servers",
            "items": items,
            "interactive": True,
            # Inventory list requests should open fully; fleet dumps can still collapse in UI.
            "default_expanded": False,
            "status_counts": payload.get("status_counts") if isinstance(payload.get("status_counts"), dict) else None,
            # Never show model-facing reply_hint / "Reply with ONE short line…" in the UI.
            "note": (
                payload.get("ui_note")
                if isinstance(payload.get("ui_note"), str) and payload.get("ui_note")
                else None
            ),
        }

    if table is None:
        alerts = payload.get("alerts")
        if isinstance(alerts, list) and alerts and isinstance(alerts[0], dict):
            headers = ["ID", "Сервер", "Severity", "Тип", "Заголовок"]
            rows = [
                [
                    a.get("id", ""),
                    a.get("server_name", ""),
                    a.get("severity", ""),
                    a.get("alert_type", ""),
                    (a.get("title") or "")[:80],
                ]
                for a in alerts[:40]
            ]
            items = [
                {
                    "id": a.get("id"),
                    "server_id": a.get("server_id"),
                    "server_name": a.get("server_name") or "",
                    "severity": a.get("severity") or "",
                    "title": a.get("title") or "",
                    "alert_type": a.get("alert_type") or "",
                }
                for a in alerts[:40]
            ]
            table = {
                "title": f"Алерты · {len(rows)}",
                "headers": headers,
                "rows": rows,
                "kind": "alerts",
                "items": items,
                "interactive": True,
            }

    if table is None:
        agents = payload.get("agents")
        # agents.list (and similar) — interactive start/stop panel in chat
        if (
            isinstance(agents, list)
            and agents
            and isinstance(agents[0], dict)
            and (
                "mode" in agents[0]
                or "active_run_id" in agents[0]
                or "agent_type" in agents[0]
                or action_type in {"agents.list", "agents_list", "agent.list"}
            )
        ):
            headers = ["ID", "Имя", "Mode", "Серверы", "Статус", "Run"]
            rows = []
            items = []
            for a in agents[:60]:
                server_names = a.get("server_names") if isinstance(a.get("server_names"), list) else []
                servers_s = ", ".join(str(n) for n in server_names[:3]) or "—"
                if len(server_names) > 3:
                    servers_s += f" +{len(server_names) - 3}"
                active_id = a.get("active_run_id")
                last_st = a.get("active_run_status") or a.get("last_run_status") or "—"
                run_label = f"#{active_id}" if active_id else (f"#{a.get('last_run_id')}" if a.get("last_run_id") else "—")
                rows.append(
                    [
                        a.get("id", ""),
                        a.get("name", ""),
                        a.get("mode") or a.get("mode_display") or "",
                        servers_s,
                        last_st,
                        run_label,
                    ]
                )
                items.append(
                    {
                        "id": a.get("id"),
                        "name": a.get("name") or "",
                        "mode": a.get("mode") or "",
                        "mode_display": a.get("mode_display") or a.get("mode") or "",
                        "agent_type": a.get("agent_type") or "",
                        "goal": (a.get("goal") or a.get("ai_prompt") or "")[:240],
                        "server_count": a.get("server_count") if a.get("server_count") is not None else len(server_names),
                        "server_ids": a.get("server_ids") if isinstance(a.get("server_ids"), list) else [],
                        "server_names": server_names,
                        "is_enabled": bool(a.get("is_enabled", True)),
                        "schedule_minutes": a.get("schedule_minutes") or 0,
                        "schedule_state": a.get("schedule_state") or "",
                        "due_now": bool(a.get("due_now")),
                        "last_run_at": a.get("last_run_at"),
                        "last_run_status": a.get("last_run_status"),
                        "last_run_id": a.get("last_run_id"),
                        "active_run_id": active_id,
                        "active_run_status": a.get("active_run_status"),
                        "active_run_started_at": a.get("active_run_started_at"),
                        "active_run_iterations": a.get("active_run_iterations") or 0,
                        "active_run_server_name": a.get("active_run_server_name") or "",
                        "active_run_pending_question": a.get("active_run_pending_question") or "",
                        "max_iterations": a.get("max_iterations") or 0,
                        "detail_url": "/agents",
                        "run_url": f"/agents/run/{active_id}" if active_id else (
                            f"/agents/run/{a.get('last_run_id')}" if a.get("last_run_id") else "/agents"
                        ),
                    }
                )
            table = {
                "title": f"Агенты · {payload.get('count', len(rows))}",
                "headers": headers,
                "rows": rows,
                "kind": "agents",
                "items": items,
                "interactive": True,
            }

    if table is None:
        preds = payload.get("predictions")
        forecast_action = action_type in {
            "operator.server_forecasts",
            "operator_server_forecasts",
            "server_forecasts",
            "forecasts",
        }
        if isinstance(preds, list) and (
            forecast_action
            or (preds and isinstance(preds[0], dict) and ("kind" in preds[0] or "eta_days" in preds[0]))
        ):
            headers = ["Сервер", "Kind", "Target", "Severity", "ETA дн"]
            rows = []
            items = []
            for p in (preds or [])[:40]:
                if not isinstance(p, dict):
                    continue
                rows.append(
                    [
                        p.get("server_name") or p.get("server") or "",
                        p.get("kind", ""),
                        p.get("target", ""),
                        p.get("severity", ""),
                        p.get("eta_days", ""),
                    ]
                )
                series = p.get("series") if isinstance(p.get("series"), list) else []
                series_nums = []
                for v in series[:48]:
                    try:
                        series_nums.append(float(v))
                    except (TypeError, ValueError):
                        continue
                items.append(
                    {
                        "id": p.get("id"),
                        "server_id": p.get("server_id"),
                        "server_name": p.get("server_name") or p.get("server") or "",
                        "kind": p.get("kind") or "",
                        "target": p.get("target") or "",
                        "severity": p.get("severity") or "",
                        "eta_days": p.get("eta_days"),
                        "current_value": p.get("current_value"),
                        "threshold": p.get("threshold"),
                        "unit": p.get("unit") or "",
                        "slope_per_day": p.get("slope_per_day"),
                        "series": series_nums,
                        "message": p.get("message") or "",
                    }
                )
            table = {
                "title": f"Прогнозы · {payload.get('count', len(items))}",
                "headers": headers,
                "rows": rows,
                "kind": "forecasts",
                "items": items,
                "interactive": True,
                "empty": len(items) == 0,
                "summary": str(payload.get("summary") or ("ok" if not items else len(items))),
            }

    if table is None:
        matrix = payload.get("matrix")
        if isinstance(matrix, list) and matrix and isinstance(matrix[0], dict):
            headers = ["Сервер", "OK", "Exit", "Вывод / ошибка"]
            rows = []
            for row in matrix[:60]:
                out = str(row.get("output") or row.get("error") or "")[:120]
                rows.append(
                    [
                        row.get("server_name") or row.get("server_id") or "",
                        "ok" if row.get("ok") else "fail",
                        row.get("exit_code", ""),
                        out,
                    ]
                )
            table = {
                "title": f"Fan-out · ok {payload.get('ok_count', '?')} / fail {payload.get('fail_count', '?')}",
                "headers": headers,
                "rows": rows,
                "kind": "fanout",
            }

    if not table:
        return
    meta = dict(message.metadata or {})
    # Keep multiple tables if needed
    existing = meta.get("tables") if isinstance(meta.get("tables"), list) else []
    existing = list(existing) + [table]
    meta["tables"] = existing[-5:]
    meta["table"] = table  # latest for simple consumers
    if table.get("kind") == "servers":
        meta["inventory_card"] = True
        meta["inventory_count"] = len(table.get("items") or table.get("rows") or [])
        if isinstance(table.get("status_counts"), dict):
            meta["inventory_status_counts"] = table["status_counts"]
    message.metadata = meta
    message.save(update_fields=["metadata"])
