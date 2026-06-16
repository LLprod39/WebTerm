from __future__ import annotations

from typing import Any

from app.tools.ssh_tools import ssh_manager
from servers.linux_ui_commands import CAPABILITIES_COMMAND
from servers.linux_ui_parsers import _as_bool, _as_int, _parse_key_value_lines
from servers.models import Server


async def _run_command(server: Server, *, secret: str = "", command: str) -> str:
    result = await _run_command_result(server, secret=secret, command=command)
    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    return stdout if stdout.strip() else stderr


async def _run_command_result(server: Server, *, secret: str = "", command: str) -> dict[str, Any]:
    conn_id = await ssh_manager.connect(
        host=server.host,
        username=server.username,
        password=secret or None,
        key_path=server.key_path if server.auth_method in ["key", "key_password"] else None,
        port=server.port,
        network_config=server.network_config or {},
        server=server,
    )
    try:
        result = await ssh_manager.execute(conn_id, command)
        return {
            "stdout": str(result.get("stdout") or ""),
            "stderr": str(result.get("stderr") or ""),
            "exit_code": _as_int(str(result.get("exit_code"))) or 0,
        }
    finally:
        await ssh_manager.disconnect(conn_id)


async def get_linux_ui_capabilities(server: Server, *, secret: str = "") -> dict[str, Any]:
    raw = await _run_command(server, secret=secret, command=CAPABILITIES_COMMAND)
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
