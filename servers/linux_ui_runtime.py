from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async

from app.sudo_policy import SUDO_POLICY_APPROVED, prepare_sudo_command
from app.tools.ssh_tools import _build_env_exports
from servers.linux_ui_commands import CAPABILITIES_COMMAND
from servers.linux_ui_parsers import _as_bool, _parse_key_value_lines
from servers.models import Server
from servers.secret_utils import get_server_sudo_secret
from servers.services.ssh_pool import ssh_connection_pool


async def _run_command(server: Server, *, secret: str = "", command: str, user_id: int | None = None) -> str:
    result = await _run_command_result(server, secret=secret, command=command, user_id=user_id)
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    return stdout if stdout.strip() else stderr


async def _run_command_result(
    server: Server, *, secret: str = "", command: str, user_id: int | None = None
) -> dict[str, Any]:
    try:
        final_command = command
        environment = (server.network_config or {}).get("environment")
        if environment:
            if not isinstance(environment, dict):
                raise ValueError("network_config.environment must be an object")
            exports = _build_env_exports(environment)
            if exports:
                final_command = "; ".join(exports) + "; " + command

        sudo_mode = getattr(server, "sudo_auth_mode", "none") or "none"
        sudo_password = ""
        if sudo_mode == "stored_password":
            try:
                sudo_password = await sync_to_async(get_server_sudo_secret, thread_sensitive=True)(server) or ""
            except Exception:
                sudo_password = ""
        prepared = prepare_sudo_command(
            final_command,
            SUDO_POLICY_APPROVED,
            sudo_auth_mode=sudo_mode,
            sudo_password=sudo_password,
        )
        run_kwargs: dict[str, Any] = {"check": False}
        if prepared.input_text is not None:
            run_kwargs["input"] = prepared.input_text
        result = await ssh_connection_pool.run_command(
            server,
            prepared.command,
            secret=secret,
            user_id=user_id,
            **run_kwargs,
        )
        return {
            "stdout": str(result.stdout or ""),
            "stderr": str(result.stderr or ""),
            "exit_code": result.exit_status if result.exit_status is not None else -1,
            "success": result.exit_status == 0,
            "sudo_notes": list(prepared.notes),
        }
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "exit_code": -1, "success": False}


async def get_linux_ui_capabilities(server: Server, *, secret: str = "", user_id: int | None = None) -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=CAPABILITIES_COMMAND, user_id=user_id)
    parsed = _parse_key_value_lines(raw)

    commands = {
        "systemctl": _as_bool(parsed.get("cmd_systemctl")),
        "journalctl": _as_bool(parsed.get("cmd_journalctl")),
        "docker": _as_bool(parsed.get("cmd_docker")),
        "ss": _as_bool(parsed.get("cmd_ss")),
        "ip": _as_bool(parsed.get("cmd_ip")),
        "apt": _as_bool(parsed.get("cmd_apt")) or _as_bool(parsed.get("cmd_apt-get")),
        "dnf": _as_bool(parsed.get("cmd_dnf")),
        "yum": _as_bool(parsed.get("cmd_yum")),
        "python3": _as_bool(parsed.get("cmd_python3")),
        "bash": _as_bool(parsed.get("cmd_bash")),
        "sh": _as_bool(parsed.get("cmd_sh")),
    }

    package_manager = None
    if commands["apt"]:
        package_manager = "apt"
    elif commands["dnf"]:
        package_manager = "dnf"
    elif commands["yum"]:
        package_manager = "yum"

    return {
        "hostname": parsed.get("hostname") or server.host,
        "current_user": parsed.get("current_user") or server.username,
        "os_name": parsed.get("os_name") or "",
        "os_id": parsed.get("os_id") or "",
        "kernel": parsed.get("kernel") or "",
        "is_systemd": _as_bool(parsed.get("is_systemd")),
        "package_manager": package_manager,
        "commands": commands,
        "available_apps": {
            "overview": True,
            "files": True,
            "terminal": True,
            "ai": True,
            "text_editor": True,
            "quick_run": commands["bash"] or commands["sh"],
            "settings": commands["bash"] or commands["sh"],
            "services": commands["systemctl"],
            "logs": commands["journalctl"],
            "processes": True,
            "disk": True,
            "network": commands["ss"] or commands["ip"],
            "docker": commands["docker"],
            "packages": bool(package_manager),
        },
    }
