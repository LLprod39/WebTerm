from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import Server
from servers.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker


class Command(BaseCommand):
    help = "Run layered server memory dreams: nearline compaction, nightly distillation, or weekly archive/repair."

    def add_arguments(self, parser):
        parser.add_argument("--server-id", type=int, action="append", dest="server_ids", help="Process only selected server id")
        parser.add_argument("--limit", type=int, default=100, help="Maximum number of servers to inspect per cycle")
        parser.add_argument("--interval", type=int, default=300, help="Daemon poll interval in seconds")
        parser.add_argument("--daemon", action="store_true", help="Run continuously until interrupted")
        parser.add_argument("--once", action="store_true", help="Run one consolidation cycle and exit")
        parser.add_argument("--keep-noise", action="store_true", help="Do not deactivate older noisy run entries")
        parser.add_argument(
            "--job-kind",
            choices=["nearline", "nightly", "weekly", "hybrid"],
            default="hybrid",
            help="Dream cycle mode",
        )
        parser.add_argument("--lease-seconds", type=int, default=180, help="Worker lease duration in seconds")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")

    def handle(self, *args, **options):
        interval = max(60, int(options["interval"]))
        daemon = bool(options["daemon"])
        once = bool(options["once"])
        limit = max(1, min(int(options["limit"]), 500))
        server_ids = options.get("server_ids") or []
        job_kind = str(options.get("job_kind") or "hybrid")
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        worker_key = str(options.get("worker_key") or "default").strip() or "default"

        state = claim_background_worker(
            "memory_dreams",
            worker_key=worker_key,
            command="python manage.py run_memory_dreams",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Memory dreams worker {worker_key!r} is already leased by another process"))
            return

        summary = {
            "servers": 0,
            "updated_notes": 0,
            "created_versions": 0,
            "archived_records": 0,
            "compacted_groups": 0,
            "skipped": 0,
        }
        self.stdout.write("Starting server memory dreams...")
        try:
            if once or not daemon:
                summary = self._tick(limit=limit, server_ids=server_ids, job_kind=job_kind, worker_key=worker_key, lease_seconds=lease_seconds)
                self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
                return

            while True:
                summary = self._tick(limit=limit, server_ids=server_ids, job_kind=job_kind, worker_key=worker_key, lease_seconds=lease_seconds)
                self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
                self.stdout.write(f"Next memory dream cycle in {interval}s...")
                time.sleep(interval)
        finally:
            stop_background_worker("memory_dreams", worker_key=worker_key, summary=summary)

    def _tick(self, *, limit: int, server_ids: list[int], job_kind: str, worker_key: str, lease_seconds: int) -> dict:
        qs = Server.objects.filter(is_active=True).order_by("id")
        if server_ids:
            qs = qs.filter(id__in=server_ids)

        store = DjangoServerMemoryStore()
        summary = {
            "servers": 0,
            "updated_notes": 0,
            "created_versions": 0,
            "archived_records": 0,
            "compacted_groups": 0,
            "skipped": 0,
        }
        heartbeat_background_worker(
            "memory_dreams",
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            cycle_started=True,
        )

        for server in qs[:limit]:
            heartbeat_background_worker(
                "memory_dreams",
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                summary=summary | {"active_server_id": server.id},
            )
            result = store._run_dream_cycle_sync(server.id, job_kind=job_kind, respect_schedule=True)
            dream = result.get("dream") or {}
            repair = result.get("repair") or {}
            summary["servers"] += 1
            if result.get("skipped"):
                summary["skipped"] += 1
                self.stdout.write(f"{server.id} {server.name}: skipped ({result.get('reason') or 'policy'})")
                continue
            summary["updated_notes"] += int(dream.get("updated_notes") or 0)
            summary["created_versions"] += int(dream.get("created_versions") or 0)
            summary["archived_records"] += int(repair.get("archived_records") or 0)
            summary["compacted_groups"] += int(result.get("compacted_groups") or 0)
            self.stdout.write(
                f"{server.id} {server.name}: "
                f"job={job_kind} "
                f"compacted={result.get('compacted_groups', 0)} "
                f"updated_notes={dream.get('updated_notes', 0)} "
                f"created_versions={dream.get('created_versions', 0)} "
                f"archived={repair.get('archived_records', 0)}"
            )

        heartbeat_background_worker(
            "memory_dreams",
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            summary=summary,
            cycle_finished=True,
        )
        return summary

    @staticmethod
    def _format_summary(summary: dict) -> str:
        return (
            f"servers={summary.get('servers', 0)} "
            f"skipped={summary.get('skipped', 0)} "
            f"updated_notes={summary.get('updated_notes', 0)} "
            f"created_versions={summary.get('created_versions', 0)} "
            f"compacted_groups={summary.get('compacted_groups', 0)} "
            f"archived_records={summary.get('archived_records', 0)}"
        )
