from __future__ import annotations

from asgiref.sync import sync_to_async
from django.utils import timezone

from servers import linux_ui
from servers.models import ServerAlert
from servers.monitoring.monitor import _decrypt_server_secret
from servers.services.server_query import get_servers_for_user
from servers.sftp import read_text_file, write_text_file


class ServersOpsRuntimeProvider:
    """Adapter exposing server operations through the app-level ops runtime port."""

    def log_sources(self) -> set[str]:
        return set(linux_ui.LOG_SOURCES)

    async def get_owned_server(self, user, server_id: int):
        def _lookup():
            return get_servers_for_user(user).filter(user=user, pk=server_id).order_by("-updated_at").first()

        return await sync_to_async(_lookup)()

    async def server_secret(self, server) -> str:
        return await sync_to_async(_decrypt_server_secret, thread_sensitive=True)(server)

    async def run_command_result(self, server, *, secret: str = "", command: str):
        return await linux_ui._run_command_result(server, secret=secret, command=command)

    async def get_linux_ui_capabilities(self, server, *, secret: str = ""):
        return await linux_ui.get_linux_ui_capabilities(server, secret=secret)

    async def get_linux_ui_disk(self, server, *, secret: str = ""):
        return await linux_ui.get_linux_ui_disk(server, secret=secret)

    async def get_linux_ui_docker(self, server, *, secret: str = ""):
        return await linux_ui.get_linux_ui_docker(server, secret=secret)

    async def get_linux_ui_docker_logs(self, server, *, secret: str = "", container: str = "", lines: int = 80):
        return await linux_ui.get_linux_ui_docker_logs(server, secret=secret, container=container, lines=lines)

    async def get_linux_ui_logs(
        self, server, *, secret: str = "", source: str = "journal", lines: int = 120, service: str = ""
    ):
        return await linux_ui.get_linux_ui_logs(server, secret=secret, source=source, lines=lines, service=service)

    async def get_linux_ui_network(self, server, *, secret: str = ""):
        return await linux_ui.get_linux_ui_network(server, secret=secret)

    async def get_linux_ui_overview(self, server, *, secret: str = ""):
        return await linux_ui.get_linux_ui_overview(server, secret=secret)

    async def get_linux_ui_packages(self, server, *, secret: str = ""):
        return await linux_ui.get_linux_ui_packages(server, secret=secret)

    async def get_linux_ui_processes(self, server, *, secret: str = "", limit: int = 80):
        return await linux_ui.get_linux_ui_processes(server, secret=secret, limit=limit)

    async def get_linux_ui_service_logs(self, server, *, secret: str = "", service: str = "", lines: int = 80):
        return await linux_ui.get_linux_ui_service_logs(server, secret=secret, service=service, lines=lines)

    async def get_linux_ui_services(self, server, *, secret: str = "", limit: int = 120):
        return await linux_ui.get_linux_ui_services(server, secret=secret, limit=limit)

    async def run_linux_ui_docker_action(self, server, *, secret: str = "", container: str = "", action: str = ""):
        return await linux_ui.run_linux_ui_docker_action(server, secret=secret, container=container, action=action)

    async def run_linux_ui_process_action(self, server, *, secret: str = "", pid="", action: str = ""):
        return await linux_ui.run_linux_ui_process_action(server, secret=secret, pid=pid, action=action)

    async def run_linux_ui_service_action(self, server, *, secret: str = "", service: str = "", action: str = ""):
        return await linux_ui.run_linux_ui_service_action(server, secret=secret, service=service, action=action)

    async def read_text_file(self, server, *, secret: str = "", path: str, max_bytes: int):
        return await read_text_file(server, secret=secret, path=path, max_bytes=max_bytes)

    async def write_text_file(self, server, *, secret: str = "", path: str, content: str, max_bytes: int):
        return await write_text_file(server, secret=secret, path=path, content=content, max_bytes=max_bytes)

    async def update_alert(self, *, user, alert_id: int, action: str, dry_run: bool = False):
        def _resolve_alert():
            alert = ServerAlert.objects.select_related("server").filter(id=alert_id, server__user=user).first()
            if alert is None:
                return None
            before = {
                "is_resolved": alert.is_resolved,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
            if action == "resolve" and not dry_run:
                alert.is_resolved = True
                alert.resolved_at = timezone.now()
                alert.resolved_by = user if getattr(user, "is_authenticated", False) else None
                alert.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])
            return {
                "id": alert.id,
                "title": alert.title,
                "server_name": alert.server.name,
                "is_resolved": True if dry_run and action == "resolve" else alert.is_resolved,
                "resolved_at": (
                    "<set-at-execution>"
                    if dry_run and action == "resolve"
                    else alert.resolved_at.isoformat()
                    if alert.resolved_at
                    else None
                ),
                "before": before,
                "dry_run": dry_run,
            }

        return await sync_to_async(_resolve_alert, thread_sensitive=True)()
