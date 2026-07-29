"""Action operator tools: metrics, memory read/write, metric series, plan (F-08a split)."""

from __future__ import annotations

from typing import Any

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.operator_tools_common import _int_arg, _server_for_user
from servers.services.server_query import user_has_server_capability


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
        "mem_percent": (getattr(sample, "memory_percent", None) if sample else getattr(health, "memory_percent", None)),
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
    server = _server_for_user(ctx.user, server_id)
    if not user_has_server_capability(server, ctx.user, "view_context"):
        raise AssistantActionError("Missing server capability: view_context", status=403)
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

        rows = ServerMetricRollup.objects.filter(
            server_id=server_id,
            metric_key=metric_key,
            granularity=ServerMetricRollup.GRANULARITY_HOUR,
        ).order_by("-bucket_start")[:48]
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
