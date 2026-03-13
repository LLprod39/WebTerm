"""
Инструменты для работы с серверами из вкладки Servers.
Используют серверы текущего пользователя (user_id из _context) и SSH.
"""
import os
from typing import Any, Dict, Optional, Tuple
from loguru import logger
from django.db.models import Q
from django.utils import timezone
from core_ui.activity import log_user_activity
from app.tools.base import BaseTool, ToolMetadata, ToolParameter
from app.tools.ssh_tools import ssh_manager
from app.tools.safety import is_dangerous_command
from asgiref.sync import sync_to_async
from servers.secret_utils import get_server_auth_secret


def _get_user_id(kwargs: Dict[str, Any]) -> Optional[int]:
    ctx = kwargs.get("_context") or {}
    user_id = ctx.get("user_id")
    # Также проверяем переменные окружения (для CLI/MCP контекста)
    if not user_id:
        env_user_id = os.environ.get("WEU_USER_ID")
        if env_user_id:
            try:
                user_id = int(env_user_id)
            except ValueError:
                pass
    return user_id


def _get_master_password(kwargs: Dict[str, Any]) -> Optional[str]:
    ctx = kwargs.get("_context") or {}
    return ctx.get("master_password") or os.environ.get("MASTER_PASSWORD")


def _get_target_server(kwargs: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """Получить целевой сервер из контекста или переменных окружения."""
    ctx = kwargs.get("_context") or {}
    
    target_server_id = ctx.get("target_server_id")
    target_server_name = ctx.get("target_server_name")
    
    # Проверяем переменные окружения (для CLI/MCP контекста)
    if not target_server_id:
        env_target_id = os.environ.get("WEU_TARGET_SERVER_ID")
        if env_target_id:
            try:
                target_server_id = int(env_target_id)
            except ValueError:
                pass
    
    if not target_server_name:
        target_server_name = os.environ.get("WEU_TARGET_SERVER_NAME")
    
    return target_server_id, target_server_name


class ServersListTool(BaseTool):
    """Список серверов пользователя из вкладки Servers (по имени можно вызывать server_execute)."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="servers_list",
            description="Список серверов текущего пользователя из раздела Servers. Возвращает id, name, host, port. Используй имя (name) или id в server_execute.",
            category="ssh",
            parameters=[],
        )

    async def execute(self, **kwargs) -> Any:
        return await sync_to_async(self._execute_sync, thread_sensitive=True)(**kwargs)

    def _execute_sync(self, **kwargs) -> Any:
        user_id = _get_user_id(kwargs)
        if not user_id:
            return "Требуется контекст пользователя (user_id). Используй только в чате WEU AI."

        # Проверяем, есть ли ограничение на целевой сервер
        target_server_id, target_server_name = _get_target_server(kwargs)
        if target_server_id:
            return (
                f"ВНИМАНИЕ: Для текущей задачи установлен целевой сервер!\n"
                f"Используй ТОЛЬКО сервер «{target_server_name}» (id={target_server_id}).\n"
                f"НЕ вызывай servers_list — целевой сервер уже определён.\n"
                f"Для выполнения команд используй: server_execute с server_name_or_id=\"{target_server_name}\""
            )

        from servers.models import Server
        now = timezone.now()
        qs = (
            Server.objects.filter(is_active=True)
            .filter(
                Q(user_id=user_id)
                | (
                    Q(shares__user_id=user_id, shares__is_revoked=False)
                    & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
                )
            )
            .distinct()
            .order_by("name")
            .values("id", "name", "host", "port", "user_id")
        )
        rows = list(qs)
        if not rows:
            return "Нет настроенных серверов. Добавь серверы в разделе Servers."
        servers = [
            {
                "id": r["id"],
                "name": r["name"],
                "host": r["host"],
                "port": r["port"],
                "access": "owner" if r["user_id"] == user_id else "shared",
            }
            for r in rows
        ]
        return {"servers": servers, "total": len(servers)}


class ServerExecuteTool(BaseTool):
    """Выполнить команду на сервере из раздела Servers по имени или id."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="server_execute",
            description="Выполнить команду на сервере из раздела Servers. server_name_or_id — имя (например WEU SERVER) или числовой id. command — команда, например df -h.",
            category="ssh",
            parameters=[
                ToolParameter(name="server_name_or_id", type="string", description="Имя сервера (например WEU SERVER) или его id из servers_list"),
                ToolParameter(name="command", type="string", description="Команда для выполнения (например df -h)"),
                ToolParameter(
                    name="allow_destructive",
                    type="boolean",
                    description="Разрешить потенциально опасные команды (только при явном подтверждении пользователя)",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs) -> Any:
        user_id = _get_user_id(kwargs)
        if not user_id:
            return "Требуется контекст пользователя. Используй только в чате WEU AI."
        
        ctx = kwargs.get("_context") or {}
        server_name_or_id = (kwargs.get("server_name_or_id") or "").strip()
        command = (kwargs.get("command") or "").strip()
        allow_destructive = bool(kwargs.get("allow_destructive") or ctx.get("allow_destructive"))
        
        if not server_name_or_id or not command:
            return "Нужны server_name_or_id и command."
        if is_dangerous_command(command) and not allow_destructive:
            return "Команда выглядит опасной. Нужен явный допуск allow_destructive=true после подтверждения пользователя."
        
        # Проверяем, есть ли ограничение на конкретный сервер (из workflow/task или env)
        target_server_id, target_server_name = _get_target_server(kwargs)
        
        # Находим запрошенный сервер
        server = await sync_to_async(self._get_server, thread_sensitive=True)(user_id, server_name_or_id)
        share = await sync_to_async(self._get_active_share, thread_sensitive=True)(user_id, server)
        
        if not server:
            if target_server_id:
                return f"Сервер не найден: «{server_name_or_id}». ВАЖНО: Используй ТОЛЬКО целевой сервер «{target_server_name}» (id={target_server_id})!"
            return f"Сервер не найден: «{server_name_or_id}». Вызови servers_list, чтобы увидеть доступные серверы."
        
        # Если есть ограничение на целевой сервер — проверяем
        if target_server_id and server.id != target_server_id:
            logger.warning(f"server_execute: попытка использовать сервер {server.name} (id={server.id}), но целевой сервер = {target_server_name} (id={target_server_id})")
            return (
                f"ОШИБКА: Ты пытаешься выполнить команду на сервере «{server.name}», "
                f"но для этой задачи установлен целевой сервер «{target_server_name}»!\n"
                f"Используй ТОЛЬКО: server_execute с server_name_or_id=\"{target_server_name}\""
            )
        password = None
        if server.auth_method in ("password", "key_password"):
            mp = _get_master_password(kwargs)
            try:
                password = await sync_to_async(
                    get_server_auth_secret,
                    thread_sensitive=True,
                )(server, master_password=mp or "", fallback_plain=getattr(server, "_plain_password", None) or "")
            except ValueError:
                return (
                    "Сервер требует мастер-пароль для расшифровки. "
                    "Выполни команду через Servers → Execute в интерфейсе или передай master_password в контексте."
                )
        key_path = server.key_path if server.auth_method in ("key", "key_password") else None
        try:
            # Подключение с network_config
            conn_id = await ssh_manager.connect(
                host=server.host,
                username=server.username,
                password=password,
                key_path=key_path or None,
                port=server.port,
                network_config=server.network_config or {},
                server=server,
            )
            result = await ssh_manager.execute(conn_id, command)
            await ssh_manager.disconnect(conn_id)
            out = (result.get("stdout") or "") + ("\n" + (result.get("stderr") or "") if result.get("stderr") else "")
            if not out:
                out = str(result)
            code = result.get("exit_code", -1)
            
            # Save command to history
            try:
                await sync_to_async(self._save_command_history, thread_sensitive=True)(
                    user_id=user_id,
                    server=server,
                    command=command,
                    output=out[:10000],
                    exit_code=code,
                )
            except Exception as hist_err:
                logger.debug(f"Failed to save command history: {hist_err}")

            await sync_to_async(log_user_activity, thread_sensitive=True)(
                user_id=user_id,
                category="terminal",
                action="server_tool_execute",
                status="success" if code == 0 else "error",
                description=command[:4000],
                entity_type="server",
                entity_id=str(server.id),
                entity_name=server.name,
                metadata={
                    "tool": "server_execute",
                    "exit_code": code,
                    "output_excerpt": out[:4000],
                },
            )

            # Analyze output and save AI knowledge
            try:
                await sync_to_async(self._save_knowledge, thread_sensitive=True)(
                    user_id=user_id,
                    server=server,
                    command_output=out,
                    command=command,
                    task_id=ctx.get("task_id"),
                )
            except Exception as knowledge_err:
                logger.debug(f"Failed to analyze knowledge: {knowledge_err}")

            # Добавляем информацию о network context если есть
            network_info = ""
            share_context_enabled = bool(getattr(share, "share_context", True)) if share else True
            if share_context_enabled and (server.network_config or server.corporate_context):
                network_summary = server.get_network_context_summary()
                if network_summary and network_summary != "Стандартная сеть":
                    network_info = f"\n\n=== Server Context ===\n{network_summary}\n===================="

            return f"Exit code: {code}{network_info}\n{out}"
        except Exception as e:
            logger.exception("server_execute failed")
            await sync_to_async(log_user_activity, thread_sensitive=True)(
                user_id=user_id,
                category="terminal",
                action="server_tool_execute",
                status="error",
                description=command[:4000],
                entity_type="server",
                entity_id=str(getattr(server, "id", "")),
                entity_name=getattr(server, "name", ""),
                metadata={
                    "tool": "server_execute",
                    "error": str(e)[:4000],
                },
            )
            return f"Ошибка выполнения на {server.name}: {e}"

    @staticmethod
    def _get_server(user_id: int, server_name_or_id: str):
        from servers.models import Server
        now = timezone.now()
        base_qs = (
            Server.objects.filter(is_active=True)
            .filter(
                Q(user_id=user_id)
                | (
                    Q(shares__user_id=user_id, shares__is_revoked=False)
                    & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=now))
                )
            )
            .distinct()
        )
        try:
            sid = int(server_name_or_id)
            return base_qs.filter(id=sid).first()
        except ValueError:
            return base_qs.filter(name__iexact=server_name_or_id).first()

    @staticmethod
    def _get_active_share(user_id: int, server):
        if not server or server.user_id == user_id:
            return None
        from servers.models import ServerShare

        now = timezone.now()
        return (
            ServerShare.objects.filter(server=server, user_id=user_id, is_revoked=False)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .first()
        )

    @staticmethod
    def _save_command_history(user_id: int, server, command: str, output: str, exit_code: int):
        from servers.models import ServerCommandHistory
        from django.contrib.auth.models import User
        user = User.objects.filter(id=user_id).first()
        ServerCommandHistory.objects.create(
            server=server,
            user=user,
            command=command,
            output=output,
            exit_code=exit_code
        )

    @staticmethod
    def _save_knowledge(user_id: int, server, command_output: str, command: str, task_id=None):
        from servers.knowledge_service import ServerKnowledgeService
        from django.contrib.auth.models import User
        user = User.objects.filter(id=user_id).first()
        ServerKnowledgeService.analyze_and_save_knowledge(
            server=server,
            command_output=command_output,
            command=command,
            task_id=task_id,
            user=user
        )
