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

from app.chat_server_provider import (
    get_server_names_for_user,
    get_servers_context_for_prompt,
    try_server_command_by_name,
)
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
    return get_servers_context_for_prompt(user_id)


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
    return get_server_names_for_user(user_id)


async def _try_server_command_by_name(user_id: int, message: str):
    """Run a safe server command when the user references one of their server names."""
    return await try_server_command_by_name(user_id, message)
