from __future__ import annotations

import os
import re

from asgiref.sync import sync_to_async
from loguru import logger

from app.tools.server_tools import ServerExecuteTool
from servers.models import Server
from servers.secret_utils import get_server_auth_secret


class DjangoChatServerProvider:
    """Server-domain implementation of chat server context helpers."""

    def get_servers_context_for_prompt(self, user_id: int) -> str:
        if not user_id:
            return ""
        try:
            master_pwd = os.environ.get("MASTER_PASSWORD", "").strip()
            servers = list(
                Server.objects.filter(user_id=user_id).only(
                    "id",
                    "name",
                    "host",
                    "port",
                    "username",
                    "auth_method",
                    "key_path",
                    "encrypted_password",
                    "salt",
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
            logger.warning(f"get_servers_context_for_prompt error: {exc}")
            return ""

    def get_server_names_for_user(self, user_id: int) -> list[str]:
        return list(Server.objects.filter(user_id=user_id).values_list("name", flat=True))

    async def try_server_command_by_name(self, user_id: int, message: str) -> str | None:
        if not user_id or not (message or "").strip():
            return None
        try:
            msg = (message or "").strip().lower()
            raw = await sync_to_async(self.get_server_names_for_user, thread_sensitive=True)(user_id)
            names = sorted(
                [name for name in raw if (name or "").strip()], key=lambda x: len((x or "").strip()), reverse=True
            )
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
