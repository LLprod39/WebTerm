from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ServerToolGateway(Protocol):
    def list_servers(self, user_id: int) -> list[Mapping[str, Any]]: ...

    def get_server(self, user_id: int, server_name_or_id: str) -> Any | None: ...

    def get_active_share(self, user_id: int, server: Any) -> Any | None: ...

    def save_command_history(self, user_id: int, server: Any, command: str, output: str, exit_code: int) -> None: ...

    def save_knowledge(
        self,
        user_id: int,
        server: Any,
        command_output: str,
        command: str,
        task_id: Any = None,
    ) -> None: ...


_server_tool_gateway: ServerToolGateway | None = None


def register_server_tool_gateway(gateway: ServerToolGateway | None) -> None:
    """Register the app-level gateway for server-domain tool operations."""
    global _server_tool_gateway
    _server_tool_gateway = gateway


def list_servers_for_tool(user_id: int) -> list[Mapping[str, Any]]:
    if _server_tool_gateway is None:
        return []
    return list(_server_tool_gateway.list_servers(user_id))


def get_tool_server(user_id: int, server_name_or_id: str) -> Any | None:
    if _server_tool_gateway is None:
        return None
    return _server_tool_gateway.get_server(user_id, server_name_or_id)


def get_tool_active_share(user_id: int, server: Any) -> Any | None:
    if _server_tool_gateway is None:
        return None
    return _server_tool_gateway.get_active_share(user_id, server)


def save_tool_command_history(user_id: int, server: Any, command: str, output: str, exit_code: int) -> None:
    if _server_tool_gateway is None:
        return
    _server_tool_gateway.save_command_history(user_id, server, command, output, exit_code)


def save_tool_knowledge(user_id: int, server: Any, command_output: str, command: str, task_id: Any = None) -> None:
    if _server_tool_gateway is None:
        return
    _server_tool_gateway.save_knowledge(user_id, server, command_output, command, task_id=task_id)
