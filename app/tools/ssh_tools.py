"""
SSH Agent Tool for Remote Operations
Allows the agent to connect to SSH servers and execute commands
"""
import re
import secrets
import shlex
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async
from django.conf import settings
from loguru import logger

from app.execution_policy import build_execution_policy_audit_metadata
from app.sudo_policy import SUDO_POLICY_APPROVED, prepare_sudo_command
from app.tools.activity_provider import get_tool_audit_context, log_tool_user_activity
from app.tools.base import BaseTool, ToolMetadata, ToolParameter
from app.tools.safety import evaluate_command_safety
from app.tools.server_secret_provider import get_server_sudo_secret
from app.tools.ssh_host_key_provider import ensure_server_known_hosts, parse_host_port_value, tofu_known_hosts_for_host

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _build_env_exports(env_vars: dict[str, Any]) -> list[str]:
    exports: list[str] = []
    for raw_key, raw_value in env_vars.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        if not _ENV_NAME_RE.match(key):
            raise ValueError(f"Invalid environment variable name: {key}")
        if raw_value is None:
            continue
        value = str(raw_value)
        if not value:
            continue
        exports.append(f"export {key}={shlex.quote(value)}")
    return exports


class SSHConnectionManager:
    """Manages SSH connections"""

    def __init__(self):
        self.connections: dict[str, asyncssh.SSHClientConnection] = {}

    async def connect(
        self,
        host: str,
        username: str,
        password: str | None = None,
        key_path: str | None = None,
        port: int = 22,
        network_config: dict | None = None,
        server: Any | None = None,
        refresh_host_key: bool = False,
    ) -> str:
        """
        Establish SSH connection с учётом network_config

        Args:
            network_config: Конфигурация корпоративной сети:
                - proxy: {http_proxy, https_proxy, no_proxy}
                - vpn: {required, type, notes}
                - network: {bastion_host, subnet, gateway}
                - firewall: {inbound_ports, outbound_restrictions}
                - environment: {HTTP_PROXY, custom_vars, ...}

        Returns:
            connection ID
        """
        normalized_host, normalized_port = parse_host_port_value(host, port)
        conn_id = f"{username}@{normalized_host}:{normalized_port}:{secrets.token_hex(4)}"

        try:
            logger.info(f"Connecting to {conn_id}...")
            effective_network_config = network_config or getattr(server, "network_config", None) or {}

            if server is not None:
                known_hosts = await ensure_server_known_hosts(server, refresh=refresh_host_key)
            else:
                known_hosts, _trusted_record = await tofu_known_hosts_for_host(
                    normalized_host,
                    normalized_port,
                    network_config=effective_network_config,
                )

            # Prepare connection options
            options = {
                "known_hosts": known_hosts,
                "connect_timeout": max(1, int(getattr(settings, "SSH_CONNECT_TIMEOUT_SECONDS", 10) or 10)),
                "login_timeout": max(1, int(getattr(settings, "SSH_LOGIN_TIMEOUT_SECONDS", 20) or 20)),
                "keepalive_interval": max(1, int(getattr(settings, "SSH_KEEPALIVE_INTERVAL_SECONDS", 20) or 20)),
                "keepalive_count_max": max(1, int(getattr(settings, "SSH_KEEPALIVE_COUNT_MAX", 3) or 3)),
            }

            # Network config handling
            if effective_network_config:
                nc = effective_network_config

                # Bastion/Jump host
                bastion = nc.get('network', {}).get('bastion_host')
                if bastion:
                    # Format: host:port или host
                    if ':' in bastion:
                        jump_host, jump_port = bastion.split(':')
                        options['jump_host'] = (jump_host, int(jump_port))
                    else:
                        options['jump_host'] = bastion
                    logger.info(f"Using bastion host: {bastion}")

                # Proxy command (для работы через HTTP прокси)
                proxy = nc.get('proxy', {}).get('http_proxy')
                if proxy:
                    # Используем ProxyCommand через netcat
                    # Формат прокси: http://proxy.corp.com:8080
                    proxy_url = proxy.replace('http://', '').replace('https://', '')
                    if ':' in proxy_url:
                        proxy_host, proxy_port = proxy_url.split(':')
                        # ProxyCommand: nc -X connect -x proxy:port %h %p
                        options['tunnel'] = (proxy_host, int(proxy_port))
                    logger.info(f"Using proxy: {proxy}")

                # Environment variables (для команд на удалённом сервере)
                # Сохраняем для использования в execute
                if nc.get('environment'):
                    # Будем добавлять в команды: export VAR=value && command
                    pass

            # Auth handling:
            # - password only -> password auth
            # - key only -> public key auth
            # - key + password -> encrypted private key passphrase
            if key_path:
                options['client_keys'] = [key_path]
            if password:
                if key_path:
                    options['passphrase'] = password
                else:
                    options['password'] = password

            conn = await asyncssh.connect(
                host=normalized_host,
                port=normalized_port,
                username=username,
                **options,
            )

            # Сохраняем network_config вместе с connection для использования в execute
            self.connections[conn_id] = {
                'connection': conn,
                'network_config': effective_network_config,
                'server': server,
            }
            logger.success(f"Connected to {conn_id}")
            return conn_id

        except Exception as e:
            logger.error(f"SSH connection failed: {e}")
            raise

    async def disconnect(self, conn_id: str):
        """Close SSH connection"""
        if conn_id in self.connections:
            conn_data = self.connections[conn_id]
            # Поддержка старого формата (прямой connection) и нового (dict)
            if isinstance(conn_data, dict):
                conn_data['connection'].close()
                await conn_data['connection'].wait_closed()
            else:
                conn_data.close()
                await conn_data.wait_closed()
            del self.connections[conn_id]
            logger.info(f"Disconnected from {conn_id}")

    async def execute(
        self,
        conn_id: str,
        command: str,
        *,
        sudo_auth_mode: str | None = None,
        sudo_password: str | None = None,
    ) -> dict[str, Any]:
        """Execute command on remote host с учётом network_config"""
        if conn_id not in self.connections:
            raise ValueError(f"No active connection: {conn_id}")

        try:
            conn_data = self.connections[conn_id]

            if isinstance(conn_data, dict):
                conn = conn_data['connection']
                network_config = conn_data.get('network_config') or {}
                server = conn_data.get('server')
            else:
                conn = conn_data
                network_config = {}
                server = None

            # Добавляем environment variables из network_config
            final_command = command
            if network_config.get('environment'):
                env_vars = network_config['environment']
                if not isinstance(env_vars, dict):
                    raise ValueError("network_config.environment must be an object")
                exports = _build_env_exports(env_vars)

                if exports:
                    final_command = "; ".join(exports) + "; " + command
                    logger.debug("Applying {} environment variable(s) to SSH command", len(exports))

            resolved_sudo_auth_mode = sudo_auth_mode or getattr(server, "sudo_auth_mode", "none")
            resolved_sudo_password = sudo_password or ""
            if not resolved_sudo_password and getattr(server, "sudo_auth_mode", "none") == "stored_password":
                resolved_sudo_password = await sync_to_async(
                    get_server_sudo_secret,
                    thread_sensitive=True,
                )(server)
            prepared = prepare_sudo_command(
                final_command,
                SUDO_POLICY_APPROVED,
                sudo_auth_mode=resolved_sudo_auth_mode,
                sudo_password=resolved_sudo_password,
            )
            run_kwargs: dict[str, Any] = {"check": False}
            if prepared.input_text is not None:
                run_kwargs["input"] = prepared.input_text

            result = await conn.run(prepared.command, **run_kwargs)

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_status,
                "success": result.exit_status == 0,
                "sudo_notes": list(prepared.notes),
            }
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "success": False
            }


# Global SSH manager instance
ssh_manager = SSHConnectionManager()


class SSHConnectTool(BaseTool):
    """Tool for establishing SSH connections"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ssh_connect",
            description="Connect to a remote server via SSH",
            category="ssh",
            parameters=[
                ToolParameter(name="host", type="string", description="SSH host address"),
                ToolParameter(name="username", type="string", description="SSH username"),
                ToolParameter(name="password", type="string", description="SSH password (optional)", required=False),
                ToolParameter(name="key_path", type="string", description="Path to SSH private key (optional)", required=False),
                ToolParameter(name="port", type="number", description="SSH port", required=False, default=22),
            ]
        )

    async def execute(self, host: str, username: str, password: str | None = None,
                     key_path: str | None = None, port: int = 22) -> str:
        """Execute SSH connection"""
        conn_id = await ssh_manager.connect(host, username, password, key_path, port)
        return f"Successfully connected to {conn_id}. Use this ID for subsequent SSH commands."


class SSHExecuteTool(BaseTool):
    """Tool for executing commands over SSH"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ssh_execute",
            description="Execute a command on a remote SSH server",
            category="ssh",
            parameters=[
                ToolParameter(name="conn_id", type="string", description="SSH connection ID (from ssh_connect)"),
                ToolParameter(name="command", type="string", description="Command to execute"),
                ToolParameter(
                    name="allow_destructive",
                    type="boolean",
                    description="Allow potentially destructive commands (explicit user confirmation required)",
                    required=False,
                ),
            ]
        )

    async def execute(
        self,
        conn_id: str,
        command: str,
        allow_destructive: bool = False,
        sudo_auth_mode: str | None = None,
        sudo_password: str | None = None,
    ) -> dict[str, Any]:
        """Execute command over SSH"""
        audit_ctx = get_tool_audit_context()
        command_risk = evaluate_command_safety(command)
        policy_metadata = build_execution_policy_audit_metadata(
            tool_name="ssh_execute",
            args={"conn_id": conn_id, "command": command},
            mode="DIRECT",
            allowed=not command_risk.is_dangerous or allow_destructive,
            sandbox_profile="ops_mutation" if command_risk.is_dangerous and allow_destructive else "ops_read",
            reason="dangerous_command_requires_allow_destructive" if command_risk.is_dangerous and not allow_destructive else "",
            requires_approval=command_risk.is_dangerous,
            risk_categories=command_risk.categories,
            matched_patterns=command_risk.matched_patterns,
            actor=str(audit_ctx.get("user_id") or ""),
        )
        if command_risk.is_dangerous and not allow_destructive:
            await log_tool_user_activity(
                user_id=audit_ctx.get("user_id"),
                username_snapshot=str(audit_ctx.get("username_snapshot") or ""),
                category="terminal",
                action="terminal_command",
                status="error",
                description=command[:4000],
                entity_type="ssh_connection",
                entity_id=conn_id,
                entity_name=conn_id,
                metadata={
                    "tool": "ssh_execute",
                    "blocked": True,
                    "reason": "dangerous_command_requires_allow_destructive",
                    "execution_policy": policy_metadata,
                },
            )
            return {"success": False, "stderr": "Команда выглядит опасной. Нужен явный допуск allow_destructive=true.", "stdout": "", "exit_code": -1}
        try:
            result = await ssh_manager.execute(
                conn_id,
                command,
                sudo_auth_mode=sudo_auth_mode,
                sudo_password=sudo_password,
            )
        except ValueError as exc:
            result = {"success": False, "stderr": str(exc), "stdout": "", "exit_code": -1}
        output_text = (result.get("stdout") or "") + (("\n" + (result.get("stderr") or "")) if result.get("stderr") else "")
        await log_tool_user_activity(
            user_id=audit_ctx.get("user_id"),
            username_snapshot=str(audit_ctx.get("username_snapshot") or ""),
            category="terminal",
            action="terminal_command",
            status="success" if result.get("exit_code") == 0 else "error",
            description=command[:4000],
            entity_type="ssh_connection",
            entity_id=conn_id,
            entity_name=conn_id,
            metadata={
                "tool": "ssh_execute",
                "exit_code": result.get("exit_code"),
                "output_excerpt": output_text[:4000],
                "execution_policy": policy_metadata,
            },
        )
        return result


class SSHDisconnectTool(BaseTool):
    """Tool for closing SSH connections"""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="ssh_disconnect",
            description="Close an active SSH connection",
            category="ssh",
            parameters=[
                ToolParameter(name="conn_id", type="string", description="SSH connection ID to close"),
            ]
        )

    async def execute(self, conn_id: str) -> str:
        """Close SSH connection"""
        await ssh_manager.disconnect(conn_id)
        return f"Disconnected from {conn_id}"
