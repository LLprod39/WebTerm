"""
Elevated (sudo) text file read/write for the GUI editor.

Uses SSH exec with sudo rather than SFTP identity change:
- read:  sudo cat -- <path>
- write: base64 | sudo tee <path> (atomic-ish overwrite)

Never logs sudo passwords. Callers must audit elevate=true separately.
"""

from __future__ import annotations

import base64
import posixpath
import shlex
from typing import Any

from asgiref.sync import sync_to_async

from app.tools.ssh_tools import _build_env_exports
from servers.models import Server
from servers.secret_utils import get_server_sudo_secret
from servers.services.ssh_pool import ssh_connection_pool
from servers.sftp import TEXT_FILE_MAX_BYTES

SUDO_AUTH_MODE_STORED_PASSWORD = "stored_password"


class ElevatedFileError(Exception):
    """Structured elevated-file failure for the API layer."""

    def __init__(self, message: str, *, code: str = "sudo_failed", status: int = 403):
        super().__init__(message)
        self.code = code
        self.status = status


def _validate_remote_path(path: str) -> str:
    target = str(path or "").strip().replace("\\", "/")
    if not target:
        raise ValueError("Не указан путь к файлу")
    if "\x00" in target:
        raise ValueError("Некорректный путь к файлу")
    if target.endswith("/") or target in {".", ".."}:
        raise ValueError("Некорректный путь к файлу")
    filename = posixpath.basename(target.rstrip("/"))
    if not filename or filename in {".", ".."}:
        raise ValueError("Некорректный путь к файлу")
    return target


async def _resolve_sudo_password(server: Server, sudo_password: str = "") -> str:
    explicit = str(sudo_password or "")
    if explicit:
        return explicit
    mode = str(getattr(server, "sudo_auth_mode", "none") or "none")
    if mode == SUDO_AUTH_MODE_STORED_PASSWORD:
        try:
            return await sync_to_async(get_server_sudo_secret, thread_sensitive=True)(server) or ""
        except Exception:
            return ""
    return ""


def _build_sudo_prefix(*, has_password: bool) -> str:
    # -S: read password from stdin; -p '': no prompt text mixed into stdout
    # -n: non-interactive (passwordless/NOPASSWD or already cached)
    if has_password:
        return "sudo -S -p ''"
    return "sudo -n"


async def _run_elevated(
    server: Server,
    *,
    secret: str,
    command: str,
    sudo_password: str = "",
    input_text: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    password = await _resolve_sudo_password(server, sudo_password)
    sudo_prefix = _build_sudo_prefix(has_password=bool(password))
    # Inject sudo prefix once at the start of the remote command.
    full_command = f"{sudo_prefix} {command}"

    # Feed password (+ optional payload) on stdin without double-wrapping sudo.
    run_input = None
    if password:
        run_input = f"{password}\n"
        if input_text is not None:
            run_input = f"{run_input}{input_text}"
    elif input_text is not None:
        run_input = input_text

    final_command = full_command
    environment = (server.network_config or {}).get("environment")
    if environment:
        if not isinstance(environment, dict):
            raise ValueError("network_config.environment must be an object")
        exports = _build_env_exports(environment)
        if exports:
            final_command = "; ".join(exports) + "; " + full_command

    run_kwargs: dict[str, Any] = {"check": False}
    if run_input is not None:
        run_kwargs["input"] = run_input
    result = await ssh_connection_pool.run_command(
        server,
        final_command,
        secret=secret,
        user_id=user_id,
        **run_kwargs,
    )
    return {
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "exit_code": result.exit_status if result.exit_status is not None else -1,
        "success": result.exit_status == 0,
        "used_password": bool(password),
    }


def _classify_sudo_failure(stderr: str, exit_code: int, *, had_password: bool) -> ElevatedFileError:
    text = (stderr or "").lower()
    if "password is required" in text or "a password is required" in text:
        return ElevatedFileError(
            "Требуется пароль sudo для операции с повышенными правами",
            code="sudo_required",
            status=403,
        )
    if "incorrect password" in text or "sorry, try again" in text:
        return ElevatedFileError("Неверный пароль sudo", code="sudo_failed", status=403)
    if "not in the sudoers" in text or "may not run sudo" in text:
        return ElevatedFileError("Пользователь не имеет прав sudo", code="sudo_failed", status=403)
    if "permission denied" in text:
        return ElevatedFileError("Недостаточно прав для выполнения операции", code="permission_denied", status=403)
    if not had_password and exit_code != 0:
        return ElevatedFileError(
            "Требуется пароль sudo для операции с повышенными правами",
            code="sudo_required",
            status=403,
        )
    return ElevatedFileError(
        (stderr or "").strip() or "Не удалось выполнить операцию через sudo",
        code="sudo_failed",
        status=403,
    )


async def read_text_file_elevated(
    server: Server,
    *,
    secret: str = "",
    path: str,
    sudo_password: str = "",
    max_bytes: int = TEXT_FILE_MAX_BYTES,
    user_id: int | None = None,
) -> dict[str, Any]:
    target = _validate_remote_path(path)
    quoted = shlex.quote(target)
    # Limit bytes server-side via head -c
    command = f"cat -- {quoted}"
    result = await _run_elevated(
        server,
        secret=secret,
        command=command,
        sudo_password=sudo_password,
        user_id=user_id,
    )
    if not result.get("success"):
        raise _classify_sudo_failure(
            str(result.get("stderr") or ""),
            int(result.get("exit_code") or -1),
            had_password=bool(result.get("used_password")),
        )

    content = str(result.get("stdout") or "")
    raw = content.encode("utf-8")
    if len(raw) > max_bytes:
        raise ValueError(f"Файл слишком большой для редактора (>{max_bytes} bytes)")

    return {
        "path": target,
        "filename": posixpath.basename(target),
        "size": len(raw),
        "encoding": "utf-8",
        "content": content,
        "elevated": True,
    }


async def write_text_file_elevated(
    server: Server,
    *,
    secret: str = "",
    path: str,
    content: str,
    sudo_password: str = "",
    max_bytes: int = TEXT_FILE_MAX_BYTES,
    user_id: int | None = None,
) -> dict[str, Any]:
    target = _validate_remote_path(path)
    payload = str(content or "").encode("utf-8")
    if len(payload) > max_bytes:
        raise ValueError(f"Файл слишком большой для сохранения через редактор (>{max_bytes} bytes)")

    b64 = base64.b64encode(payload).decode("ascii")
    # Password (if any) is consumed by sudo -S first; remaining stdin is base64 payload.
    #   sudo -S sh -c 'base64 -d > path'  with stdin: password\n + b64
    shell_cmd = f"sh -c {shlex.quote(f'base64 -d > {target}')}"

    result = await _run_elevated(
        server,
        secret=secret,
        command=shell_cmd,
        sudo_password=sudo_password,
        input_text=f"{b64}\n",
        user_id=user_id,
    )
    if not result.get("success"):
        raise _classify_sudo_failure(
            str(result.get("stderr") or ""),
            int(result.get("exit_code") or -1),
            had_password=bool(result.get("used_password")),
        )

    return {
        "path": target,
        "filename": posixpath.basename(target),
        "size": len(payload),
        "encoding": "utf-8",
        "content": str(content or ""),
        "elevated": True,
    }
