"""
Management command to persist watcher drafts in a loop.

Usage:
    python manage.py run_watchers
    python manage.py run_watchers --once
    python manage.py run_watchers --interval 120 --limit 50
"""

from __future__ import annotations

import asyncio
import signal
import sys

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from loguru import logger

from servers.models import Server
from servers.watcher_service import WatcherService
from servers.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker


class Command(BaseCommand):
    help = "Run background watcher scans and persist operator drafts."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=180, help="Watcher scan interval in seconds (default 180)")
        parser.add_argument("--limit", type=int, default=100, help="Maximum number of servers to scan per cycle")
        parser.add_argument("--server-id", type=int, action="append", dest="server_ids", help="Only scan selected server id")
        parser.add_argument("--daemon", action="store_true", help="Accepted for supervisor compatibility; watcher runs continuously by default")
        parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
        parser.add_argument("--lease-seconds", type=int, default=180, help="Worker lease duration in seconds")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")

    def handle(self, *args, **options):
        interval = max(15, int(options["interval"]))
        limit = max(1, min(int(options["limit"]), 500))
        server_ids = options.get("server_ids") or []
        once = bool(options["once"])
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        worker_key = str(options.get("worker_key") or "default").strip() or "default"

        state = claim_background_worker(
            "watchers",
            worker_key=worker_key,
            command="python manage.py run_watchers",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Watcher worker {worker_key!r} is already leased by another process"))
            return

        summary = {}
        try:
            if once:
                summary = self._run_once(limit=limit, server_ids=server_ids, worker_key=worker_key, lease_seconds=lease_seconds)
                self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
                return

            self.stdout.write(self.style.SUCCESS(f"Starting watcher daemon (interval={interval}s, limit={limit})"))
            try:
                asyncio.run(self._run_loop(interval=interval, limit=limit, server_ids=server_ids, worker_key=worker_key, lease_seconds=lease_seconds))
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\nWatcher daemon stopped by user"))
        finally:
            stop_background_worker("watchers", worker_key=worker_key, summary=summary)

    def _scan_queryset(self, *, limit: int, server_ids: list[int]) -> dict:
        qs = Server.objects.filter(is_active=True, user__is_active=True).order_by("id")
        if server_ids:
            qs = qs.filter(id__in=server_ids)
        return WatcherService().persist_queryset(qs, limit=limit)

    def _run_once(self, *, limit: int, server_ids: list[int], worker_key: str, lease_seconds: int) -> dict:
        heartbeat_background_worker("watchers", worker_key=worker_key, lease_seconds=lease_seconds, cycle_started=True)
        summary = self._scan_queryset(limit=limit, server_ids=server_ids)
        heartbeat_background_worker(
            "watchers",
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            summary=summary,
            cycle_finished=True,
        )
        return summary

    async def _run_loop(self, *, interval: int, limit: int, server_ids: list[int], worker_key: str, lease_seconds: int):
        stop = asyncio.Event()

        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig and sys.platform != "win32":
                loop.add_signal_handler(sig, stop.set)

        cycle = 0
        while not stop.is_set():
            cycle += 1
            try:
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    "watchers",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    cycle_started=True,
                )
                summary = await sync_to_async(self._scan_queryset, thread_sensitive=True)(
                    limit=limit,
                    server_ids=server_ids,
                )
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    "watchers",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"cycle": cycle},
                    cycle_finished=True,
                )
                logger.info("Watcher cycle {} complete: {}", cycle, self._format_summary(summary))
            except Exception as exc:
                await sync_to_async(stop_background_worker, thread_sensitive=True)(
                    "watchers",
                    worker_key=worker_key,
                    error=str(exc),
                )
                logger.error("Watcher cycle {} failed: {}", cycle, exc)

            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

        logger.info("Watcher daemon shutdown complete")

    @staticmethod
    def _format_summary(summary: dict) -> str:
        persisted = summary.get("persisted") or {}
        info = summary.get("summary") or {}
        return (
            f"scanned={info.get('scanned_servers', 0)} "
            f"critical={info.get('critical', 0)} "
            f"warning={info.get('warning', 0)} "
            f"drafts={info.get('drafts', 0)} "
            f"created={persisted.get('created', 0)} "
            f"updated={persisted.get('updated', 0)} "
            f"reopened={persisted.get('reopened', 0)} "
            f"resolved={persisted.get('resolved', 0)}"
        )
