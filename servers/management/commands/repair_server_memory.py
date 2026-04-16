from __future__ import annotations

from django.core.management.base import BaseCommand

from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import Server


class Command(BaseCommand):
    help = "Decay stale server memory confidence and create revalidation notes."

    def add_arguments(self, parser):
        parser.add_argument("--server-id", type=int, action="append", dest="server_ids", help="Repair memory only for selected server id")
        parser.add_argument("--limit", type=int, default=100, help="Maximum number of servers to scan")
        parser.add_argument("--stale-days", type=int, default=30, help="Age threshold after which memory requires revalidation")
        parser.add_argument("--no-notes", action="store_true", help="Do not create revalidation notes, only decay confidence")

    def handle(self, *args, **options):
        server_ids = options.get("server_ids") or []
        limit = max(1, min(int(options["limit"]), 500))
        stale_days = max(1, int(options["stale_days"]))
        create_notes = not bool(options["no_notes"])

        qs = Server.objects.filter(is_active=True).order_by("id")
        if server_ids:
            qs = qs.filter(id__in=server_ids)

        store = DjangoServerMemoryStore()
        total_servers = 0
        total_updates = 0
        total_notes = 0

        for server in qs[:limit]:
            total_servers += 1
            result = store._repair_server_memory_sync(
                server.id,
                stale_after_days=stale_days,
                create_notes=create_notes,
            )
            total_updates += int(result.get("updated_records") or 0)
            total_notes += int(result.get("created_notes") or 0)
            self.stdout.write(
                f"{server.id} {server.name}: "
                f"updated={result.get('updated_records', 0)} "
                f"notes={result.get('created_notes', 0)} "
                f"archived={result.get('archived_records', 0)}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Server memory repair complete: servers={total_servers}, updated_records={total_updates}, created_notes={total_notes}"
            )
        )
