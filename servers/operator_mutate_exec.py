"""Operator mutate tools: command execution — run_command / run_fanout (F-08a split)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from asgiref.sync import async_to_sync
from loguru import logger

from app.assistant_actions import AssistantActionContext, AssistantActionError
from app.tools.safety import evaluate_command_safety
from servers.operator_tools_common import _int_arg, _server_for_user
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _require_ssh_server,
    _resolve_server_secret,
    _server_has_capability,
)


def _resolve_secret(ctx: AssistantActionContext, server) -> str:
    """Resolve SSH password/passphrase even without HTTP request (Operator WS).

    Order:
    1) request-aware path (session MASTER_PASSWORD / payload)
    2) managed secrets + legacy decrypt with env MASTER_PASSWORD
    3) empty string for pure key auth
    """
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    if ctx.request is not None:
        try:
            secret = _resolve_server_secret(server, ctx.request, payload)
            if secret:
                return secret
        except Exception as exc:  # noqa: BLE001
            # Fall through to request-less path before failing hard
            logger.warning("request secret resolve failed for {}: {}", server.name, exc)

    # WebSocket / background: no Django request.session — still decrypt stored secrets.
    try:
        from servers.secret_utils import get_server_auth_secret

        direct = str(payload.get("password") or "").strip()
        secret = get_server_auth_secret(server, master_password="", fallback_plain=direct)
        if secret:
            return secret
    except Exception as exc:  # noqa: BLE001
        raise AssistantActionError(f"Cannot resolve credentials: {exc}") from exc

    # key-only hosts legitimately have no password
    if getattr(server, "auth_method", "") in {"key", "key_password"}:
        return ""
    # password auth without a resolvable secret is a hard error (avoid silent Permission denied)
    if getattr(server, "auth_method", "") in {"password", "key_password"}:
        raise AssistantActionError(
            "Не удалось получить пароль сервера. "
            "Сохрани credentials в Managed Secret или задай MASTER_PASSWORD для legacy-шифрования."
        )
    return ""


def _execute_on_server(ctx: AssistantActionContext, server, command: str, *, allow_destructive: bool) -> dict[str, Any]:
    risk = evaluate_command_safety(command)
    if risk.is_dangerous and not allow_destructive:
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "blocked": True,
            "error": "Dangerous command requires allow_destructive=true after confirmation",
            "risk_categories": list(risk.categories),
        }
    # Soft guard: ai_read_only blocks non-read-ish commands unless clearly status-like.
    if (
        getattr(server, "ai_read_only", False)
        and not command.strip().startswith(
            (
                "ls",
                "cat ",
                "df",
                "free",
                "uptime",
                "ps ",
                "systemctl status",
                "journalctl",
                "uname",
                "hostname",
                "whoami",
                "id",
                "pwd",
                "echo ",
            )
        )
        and (
            risk.is_dangerous
            or any(
                token in command
                for token in (
                    "rm ",
                    "mv ",
                    "chmod",
                    "chown",
                    "systemctl restart",
                    "systemctl stop",
                    "apt ",
                    "yum ",
                    "dnf ",
                )
            )
        )
    ):
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "blocked": True,
            "error": "Server is ai_read_only — mutating command blocked",
        }

    _require_ssh_server(server)
    if not _server_has_capability(server, ctx.user, "connect_terminal"):
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "error": "Missing capability: connect_terminal",
        }

    secret = _resolve_secret(ctx, server)
    try:
        from servers.linux_ui_runtime import _run_command_result

        result = async_to_sync(_run_command_result)(server, secret=secret, command=command)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)[:500]
        # Auth/connect failures are expected operator outcomes — no full traceback spam
        if "Permission denied" in msg or "Authentication" in msg or "timed out" in msg.lower():
            logger.warning("operator run_command failed on {}: {}", server.name, msg)
        else:
            logger.exception("operator run_command failed on %s", server.name)
        return {
            "ok": False,
            "server_id": server.id,
            "server_name": server.name,
            "error": msg,
            "output": msg,
        }

    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    code = result.get("exit_status", result.get("exit_code", -1))
    out = (stdout + ("\n" + stderr if stderr else "")).strip()
    return {
        "ok": code in (0, "0", None),
        "server_id": server.id,
        "server_name": server.name,
        "exit_code": code,
        "output": out[:8000],
        "risk_categories": list(risk.categories),
    }


def run_command(ctx: AssistantActionContext) -> dict[str, Any]:
    server_id = _int_arg(ctx, "server_id")
    assert server_id is not None
    command = str(ctx.input_payload.get("command") or ctx.input_payload.get("cmd") or "").strip()
    if not command:
        raise AssistantActionError("command is required")
    allow_destructive = bool(ctx.input_payload.get("allow_destructive"))
    server = _server_for_user(ctx.user, server_id)
    result = _execute_on_server(ctx, server, command, allow_destructive=allow_destructive)
    result["target_url"] = f"/servers/{server.id}/terminal"
    result["blast_radius"] = {"server_ids": [server.id], "server_names": [server.name]}
    result["dry_run_preview"] = {"command": command, "server": server.name}
    # Simple undo heuristics
    undo = _guess_undo(command)
    if undo:
        result["undo_payload"] = {"server_id": server.id, "command": undo}
    return result


def run_fanout(ctx: AssistantActionContext) -> dict[str, Any]:
    command = str(ctx.input_payload.get("command") or ctx.input_payload.get("cmd") or "").strip()
    if not command:
        raise AssistantActionError("command is required")
    allow_destructive = bool(ctx.input_payload.get("allow_destructive"))
    raw_ids = ctx.input_payload.get("server_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        # Resolve by tags/group name optional
        tag = str(ctx.input_payload.get("tag") or "").strip()
        qs = _accessible_servers_queryset(ctx.user)
        if tag:
            qs = qs.filter(tags__icontains=tag)
        servers = list(qs.order_by("name")[:30])
    else:
        ids = []
        for item in raw_ids:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        servers = list(_accessible_servers_queryset(ctx.user).filter(id__in=ids).order_by("name")[:40])

    if not servers:
        raise AssistantActionError("No accessible servers matched")

    concurrency = max(1, min(int(ctx.input_payload.get("concurrency") or 4), 8))
    matrix: list[dict[str, Any]] = []

    def _one(server):
        return _execute_on_server(ctx, server, command, allow_destructive=allow_destructive)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_one, s): s for s in servers}
        for fut in as_completed(futures):
            try:
                matrix.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                s = futures[fut]
                matrix.append({"ok": False, "server_id": s.id, "server_name": s.name, "error": str(exc)[:300]})

    matrix.sort(key=lambda row: (not row.get("ok"), str(row.get("server_name") or "")))
    ok_count = sum(1 for row in matrix if row.get("ok"))
    return {
        "ok": ok_count == len(matrix),
        "command": command,
        "matrix": matrix,
        "ok_count": ok_count,
        "fail_count": len(matrix) - ok_count,
        "blast_radius": {
            "server_ids": [s.id for s in servers],
            "server_names": [s.name for s in servers],
            "count": len(servers),
        },
        "dry_run_preview": {"command": command, "hosts": len(servers)},
        "target_url": "/servers",
    }


def _guess_undo(command: str) -> str | None:
    cmd = command.strip()
    # Very small heuristic set — honesty over false undo
    if cmd.startswith("systemctl start "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl stop {unit}"
    if cmd.startswith("systemctl stop "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl start {unit}"
    if cmd.startswith("systemctl enable "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl disable {unit}"
    if cmd.startswith("systemctl disable "):
        unit = cmd.split(None, 2)[-1]
        return f"systemctl enable {unit}"
    return None
