"""
Helper functions for chat orchestration and Cursor CLI streaming.
"""

import asyncio
import os
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from loguru import logger

from core_ui.models import ChatSession


def _resolve_cursor_cli_command() -> str:
    """Resolve the Cursor CLI agent binary path."""
    path_from_env = (os.getenv("CURSOR_CLI_PATH") or "").strip()
    if path_from_env:
        if Path(path_from_env).exists():
            return path_from_env
        raise FileNotFoundError(f"CURSOR_CLI_PATH задан, но файл не найден: {path_from_env}")
    cfg = getattr(settings, "CLI_RUNTIME_CONFIG", None) or {}
    cursor_cfg = cfg.get("cursor") or {}
    cmd = cursor_cfg.get("command", "agent")
    if os.path.isabs(cmd):
        if not Path(cmd).exists():
            raise FileNotFoundError(f"Cursor CLI не найден: {cmd}")
        return cmd
    resolved = shutil.which(cmd)
    if not resolved:
        raise FileNotFoundError("Cursor CLI (agent) не найден. Добавьте agent в PATH или задайте CURSOR_CLI_PATH.")
    return resolved


def _get_servers_context_for_prompt(user_id: int) -> str:
    """
    Return user server context for Cursor CLI prompts.

    Includes ready SSH command hints when server secrets can be decrypted.
    """
    if not user_id:
        return ""
    try:
        from servers.models import Server
        from servers.secret_utils import get_server_auth_secret

        master_pwd = os.environ.get("MASTER_PASSWORD", "").strip()
        servers = list(
            Server.objects.filter(user_id=user_id).only(
                "id", "name", "host", "port", "username", "auth_method", "key_path", "encrypted_password", "salt"
            )
        )
        if not servers:
            return ""
        lines = [
            "\n\n=== СЕРВЕРЫ ПОЛЬЗОВАТЕЛЯ ===",
            "ВАЖНО: Данные серверов ниже. НЕ ищи их в коде!",
            "Для SSH-команд используй готовые команды подключения:",
            "",
        ]
        for server in servers:
            auth = server.auth_method or "password"
            key_path = server.key_path or ""
            pwd_decrypted = ""
            if auth in ("password", "key_password"):
                try:
                    pwd_decrypted = get_server_auth_secret(server, master_password=master_pwd)
                except Exception as exc:
                    logger.debug(f"Password decryption failed for server {server.name}: {exc}")
                    pwd_decrypted = ""
            if auth == "key" and key_path:
                cmd_hint = (
                    f"ssh -i {key_path} -o StrictHostKeyChecking=no "
                    f"{server.username}@{server.host} -p {server.port} '<COMMAND>'"
                )
            elif pwd_decrypted:
                safe_pwd = pwd_decrypted.replace("'", "'\\''")
                cmd_hint = (
                    f"sshpass -p '{safe_pwd}' ssh -o StrictHostKeyChecking=no "
                    f"{server.username}@{server.host} -p {server.port} '<COMMAND>'"
                )
            else:
                cmd_hint = (
                    f"ssh -o StrictHostKeyChecking=no {server.username}@{server.host} "
                    f"-p {server.port} '<COMMAND>'  # пароль недоступен"
                )
            lines.append(f"• {server.name}:")
            lines.append(f"    {cmd_hint}")
        lines.append("")
        lines.append("Замени <COMMAND> на нужную команду (например df -h, hostname, uptime).")
        lines.append("sshpass установлен в системе.")
        lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"_get_servers_context_for_prompt error: {exc}")
        return ""


async def _stream_cursor_cli(
    message: str,
    workspace: str,
    mode: str = "ask",
    sandbox: str = "",
    approve_mcps: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Stream a Cursor CLI response.

    ask: agent --mode=ask -p --output-format text --workspace ... --model auto ...
    agent: agent -p --force --output-format stream-json --stream-partial-output --workspace ... --model auto ...
    """
    is_agent_mode = (mode or "").strip().lower() == "agent"
    cmd_path = _resolve_cursor_cli_command()
    base_dir = str(Path(workspace).resolve()) if workspace else str(Path(settings.BASE_DIR).resolve())
    env = dict(os.environ)
    extra = getattr(settings, "CURSOR_CLI_EXTRA_ENV", None) or {}
    env.update(extra)

    extra_flags = []
    if sandbox and (sandbox.strip().lower() in ("enabled", "disabled")):
        extra_flags.extend(["--sandbox", sandbox.strip().lower()])
    if approve_mcps:
        extra_flags.append("--approve-mcps")

    if is_agent_mode:
        args = [
            cmd_path,
            "-p",
            "--force",
            "--output-format",
            "stream-json",
            "--stream-partial-output",
            "--workspace",
            base_dir,
            "--model",
            "auto",
            *extra_flags,
            message,
        ]
    else:
        args = [
            cmd_path,
            "--mode=ask",
            "-p",
            "--output-format",
            "text",
            "--workspace",
            base_dir,
            "--model",
            "auto",
            *extra_flags,
            message,
        ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=base_dir,
        env=env,
    )
    try:
        if proc.stdout:
            while True:
                chunk = await asyncio.wait_for(proc.stdout.read(8192), timeout=120.0)
                if not chunk:
                    break
                part = chunk.decode("utf-8", errors="replace")
                if part:
                    yield part
    except asyncio.TimeoutError:
        proc.kill()
        yield "\n\n⚠️ Cursor CLI превысил время ожидания (120 с)."
    finally:
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                proc.kill()
            except (ProcessLookupError, OSError) as exc:
                logger.debug(f"Process already terminated: {exc}")
        if proc.returncode and proc.returncode != 0 and proc.stderr:
            err = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
            if err:
                yield f"\n\n⚠️ Cursor CLI exit {proc.returncode}: {err[:500]}"


def _chat_history_from_session(session):
    """Build list of {role, content} from ChatMessage for orchestrator initial_history."""
    return [
        {"role": message.role, "content": message.content}
        for message in session.messages.order_by("created_at").only("role", "content")
    ]


def _load_session(user_id, chat_id):
    """Load ChatSession by user_id and chat_id."""
    return ChatSession.objects.filter(user_id=user_id, id=chat_id).select_related().first()


def _load_task_context_for_user(user_id: int, task_id) -> dict:
    """Return safe task context for chat prompts."""
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {}

    if not user_id or not task_id:
        return {}

    from django.contrib.auth.models import User
    from tasks.models import Task

    from app.services.permissions import PermissionService

    user = User.objects.filter(id=user_id).first()
    if not user:
        return {}
    task = Task.objects.filter(id=task_id).select_related("assignee", "created_by").first()
    if not task or not PermissionService.can_view_task(user, task):
        return {}

    return {
        "id": task.id,
        "title": task.title,
        "description": (task.description or "")[:1000],
        "status": task.status,
        "priority": getattr(task, "priority", "MEDIUM"),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "assignee": task.assignee.username if task.assignee else None,
    }


@sync_to_async
def _get_server_names_for_user(user_id: int):
    """Fetch server names from sync ORM for async chat handlers."""
    from servers.models import Server

    return list(Server.objects.filter(user_id=user_id).values_list("name", flat=True))


async def _try_server_command_by_name(user_id: int, message: str):
    """Run a safe server command when the user references one of their server names."""
    import re

    try:
        from app.tools.server_tools import ServerExecuteTool
    except ImportError as exc:
        logger.debug(f"ServerExecuteTool not available: {exc}")
        return None
    if not user_id or not (message or "").strip():
        return None
    try:
        msg = (message or "").strip().lower()
        raw = await _get_server_names_for_user(user_id)
        names = sorted([name for name in raw if (name or "").strip()], key=lambda x: len((x or "").strip()), reverse=True)
        if not names:
            return None

        chosen = None
        for name in names:
            normalized = (name or "").strip()
            if not normalized:
                continue
            pattern = re.escape(normalized)
            if re.search(r"(^|[^\w])" + pattern + r"([^\w]|$)", message, re.IGNORECASE):
                chosen = name
                break
        if not chosen:
            return None

        command = "df -h"
        if "место" in msg or "диск" in msg or "свободн" in msg:
            command = "df -h"
        elif "подключись" in msg or "подключиться" in msg:
            command = "hostname && echo OK"
        else:
            match = re.search(r"(?:выполни|запусти|команду)\s+([^\n.!?\]]+)", message, re.IGNORECASE)
            if match:
                cmd = match.group(1).strip().strip("\"'")
                if cmd and len(cmd) < 200:
                    command = cmd
            if "df" in msg and "df -h" not in command and "df " not in command:
                command = "df -h"
        tool = ServerExecuteTool()
        out = await tool.execute(
            server_name_or_id=chosen,
            command=command,
            _context={"user_id": user_id},
        )
        return (
            f"Результат на сервере «{chosen}» (данные из вкладки Servers):\n\n{out}"
            if isinstance(out, str)
            else str(out)
        )
    except Exception as exc:
        logger.warning(f"server_command_by_name failed: {exc}")
        return None
