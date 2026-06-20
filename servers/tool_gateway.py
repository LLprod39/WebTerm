from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from servers.knowledge_service import ServerKnowledgeService
from servers.models import Server, ServerCommandHistory, ServerShare


class DjangoServerToolGateway:
    """Django-backed implementation of server operations needed by app tools."""

    def list_servers(self, user_id: int) -> list[dict[str, Any]]:
        now = timezone.now()
        rows = (
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
        return list(rows)

    def get_server(self, user_id: int, server_name_or_id: str):
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

    def get_active_share(self, user_id: int, server):
        if not server or server.user_id == user_id:
            return None

        now = timezone.now()
        return (
            ServerShare.objects.filter(server=server, user_id=user_id, is_revoked=False)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .first()
        )

    def save_command_history(self, user_id: int, server, command: str, output: str, exit_code: int) -> None:
        user = User.objects.filter(id=user_id).first()
        ServerCommandHistory.objects.create(
            server=server,
            user=user,
            actor_kind=ServerCommandHistory.ACTOR_PIPELINE,
            source_kind=ServerCommandHistory.SOURCE_PIPELINE,
            command=command,
            output=output,
            exit_code=exit_code,
        )

    def save_knowledge(
        self,
        user_id: int,
        server,
        command_output: str,
        command: str,
        task_id: Any = None,
    ) -> None:
        user = User.objects.filter(id=user_id).first()
        ServerKnowledgeService.analyze_and_save_knowledge(
            server=server,
            command_output=command_output,
            command=command,
            task_id=task_id,
            user=user,
        )
