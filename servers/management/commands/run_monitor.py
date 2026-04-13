"""
Management command to run server health monitoring in a loop.

Usage:
    python manage.py run_monitor
    python manage.py run_monitor --quick-interval 300 --deep-interval 600
    python manage.py run_monitor --once          # single check then exit
    python manage.py run_monitor --deep --once   # single deep check then exit
"""

from __future__ import annotations

import asyncio
import signal
import sys

from django.core.management.base import BaseCommand
from loguru import logger

from servers.monitor import check_all_servers, cleanup_old_data


class Command(BaseCommand):
    help = "Run background server health monitoring (quick every 5 min, deep every 10 min)"

    def add_arguments(self, parser):
        parser.add_argument("--quick-interval", type=int, default=300, help="Quick check interval in seconds (default 300)")
        parser.add_argument("--deep-interval", type=int, default=600, help="Deep check interval in seconds (default 600)")
        parser.add_argument("--cleanup-interval", type=int, default=86400, help="Old data cleanup interval in seconds (default 86400)")
        parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent SSH connections (default 5)")
        parser.add_argument("--server-id", dest="server_ids", action="append", type=int, help="Restrict checks to one or more server IDs (repeatable)")
        parser.add_argument("--once", action="store_true", help="Run a single check and exit")
        parser.add_argument("--deep", action="store_true", help="Force deep check (with --once)")

    def handle(self, *args, **options):
        quick_interval = options["quick_interval"]
        deep_interval = options["deep_interval"]
        cleanup_interval = options["cleanup_interval"]
        concurrency = options["concurrency"]
        server_ids = options["server_ids"] or []
        once = options["once"]
        deep = options["deep"]
        scope_text = f"servers={','.join(str(item) for item in server_ids)}" if server_ids else "all active SSH servers"

        if once:
            self.stdout.write(f"Running {'deep' if deep else 'quick'} check for {scope_text}...")
            results = asyncio.run(check_all_servers(deep=deep, concurrency=concurrency, server_ids=server_ids))
            self.stdout.write(self.style.SUCCESS(f"Checked {len(results)} servers"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Starting server monitor (quick={quick_interval}s, deep={deep_interval}s, concurrency={concurrency}, scope={scope_text})"
        ))

        try:
            asyncio.run(self._run_loop(quick_interval, deep_interval, cleanup_interval, concurrency, server_ids))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nMonitor stopped by user"))

    async def _run_loop(
        self,
        quick_interval: int,
        deep_interval: int,
        cleanup_interval: int,
        concurrency: int,
        server_ids: list[int] | None = None,
    ):
        stop = asyncio.Event()

        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig and sys.platform != "win32":
                loop.add_signal_handler(sig, stop.set)

        quick_counter = 0
        deep_every_n = max(1, deep_interval // quick_interval)
        cleanup_counter = 0
        cleanup_every_n = max(1, cleanup_interval // quick_interval)

        while not stop.is_set():
            quick_counter += 1
            cleanup_counter += 1
            is_deep = quick_counter % deep_every_n == 0

            try:
                check_type = "deep" if is_deep else "quick"
                logger.info("Monitor: starting {} check (cycle {})", check_type, quick_counter)
                results = await check_all_servers(deep=is_deep, concurrency=concurrency, server_ids=server_ids)
                logger.info("Monitor: {} check done, {} servers checked", check_type, len(results))
            except Exception as exc:
                logger.error("Monitor: check cycle failed: {}", exc)

            if cleanup_counter >= cleanup_every_n:
                cleanup_counter = 0
                try:
                    await cleanup_old_data(days=7)
                except Exception as exc:
                    logger.error("Monitor: cleanup failed: {}", exc)

            try:
                await asyncio.wait_for(stop.wait(), timeout=quick_interval)
                break
            except asyncio.TimeoutError:
                pass

        logger.info("Monitor: graceful shutdown complete")
