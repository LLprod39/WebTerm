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

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from loguru import logger

from app.background_workers import STUDIO_MONITOR_WORKER
from servers.monitoring.ai_insights import run_ai_insights_for_servers
from servers.monitoring.cert_collector import collect_certificates_for_all
from servers.monitoring.forecast_persistence import run_forecast_persistence
from servers.monitoring.metrics_rollup import run_metric_rollups
from servers.monitoring.monitor import check_all_servers, cleanup_old_data
from servers.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker


class Command(BaseCommand):
    help = "Run background server health monitoring (lite TCP every 5 min, deep SSH every 10 min)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--quick-interval", type=int, default=300, help="Quick check interval in seconds (default 300)"
        )
        parser.add_argument(
            "--deep-interval", type=int, default=600, help="Deep check interval in seconds (default 600)"
        )
        parser.add_argument(
            "--cleanup-interval", type=int, default=86400, help="Old data cleanup interval in seconds (default 86400)"
        )
        parser.add_argument(
            "--rollup-interval", type=int, default=3600, help="Metric rollup interval in seconds (default 3600)"
        )
        parser.add_argument(
            "--cert-interval", type=int, default=21600, help="TLS certificate scan interval in seconds (default 21600)"
        )
        parser.add_argument(
            "--ai-interval", type=int, default=21600, help="AI insight analysis interval in seconds (default 21600)"
        )
        parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent SSH connections (default 5)")
        parser.add_argument(
            "--server-id",
            dest="server_ids",
            action="append",
            type=int,
            help="Restrict checks to one or more server IDs (repeatable)",
        )
        parser.add_argument("--once", action="store_true", help="Run a single check and exit")
        parser.add_argument("--deep", action="store_true", help="Force deep SSH check (with --once)")
        parser.add_argument(
            "--full-quick",
            action="store_true",
            help="Use full SSH quick check instead of lite TCP for quick cycles",
        )
        parser.add_argument("--lease-seconds", type=int, default=180, help="Worker heartbeat lease duration")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")

    def handle(self, *args, **options):
        quick_interval = options["quick_interval"]
        deep_interval = options["deep_interval"]
        cleanup_interval = options["cleanup_interval"]
        rollup_interval = options["rollup_interval"]
        cert_interval = options["cert_interval"]
        ai_interval = options["ai_interval"]
        concurrency = options["concurrency"]
        server_ids = options["server_ids"] or []
        once = options["once"]
        deep = options["deep"]
        lite_quick = not options.get("full_quick")
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        worker_key = str(options.get("worker_key") or "default").strip() or "default"
        scope_text = f"servers={','.join(str(item) for item in server_ids)}" if server_ids else "all active servers"

        state = claim_background_worker(
            STUDIO_MONITOR_WORKER,
            worker_key=worker_key,
            command="python manage.py run_monitor",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Monitor worker {worker_key!r} is already leased by another process"))
            return

        summary = {}
        try:
            if once:
                mode = "deep" if deep else ("lite" if lite_quick else "quick")
                self.stdout.write(f"Running {mode} check for {scope_text}...")
                heartbeat_background_worker(
                    STUDIO_MONITOR_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    cycle_started=True,
                )
                results = asyncio.run(
                    check_all_servers(
                        deep=deep,
                        lite=lite_quick and not deep,
                        concurrency=concurrency,
                        server_ids=server_ids,
                    )
                )
                summary = {"mode": mode, "checked": len(results), "errors": 0}
                heartbeat_background_worker(
                    STUDIO_MONITOR_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary,
                    cycle_finished=True,
                )
                self.stdout.write(self.style.SUCCESS(f"Checked {len(results)} servers"))
                return

            self.stdout.write(
                self.style.SUCCESS(
                    f"Starting server monitor (quick={quick_interval}s, deep={deep_interval}s, concurrency={concurrency}, scope={scope_text})"
                )
            )

            try:
                summary = asyncio.run(
                    self._run_loop(
                        quick_interval,
                        deep_interval,
                        cleanup_interval,
                        concurrency,
                        server_ids,
                        lite_quick,
                        worker_key,
                        lease_seconds,
                        rollup_interval=rollup_interval,
                        cert_interval=cert_interval,
                        ai_interval=ai_interval,
                    )
                )
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\nMonitor stopped by user"))
        finally:
            stop_background_worker(STUDIO_MONITOR_WORKER, worker_key=worker_key, summary=summary)

    async def _run_loop(
        self,
        quick_interval: int,
        deep_interval: int,
        cleanup_interval: int,
        concurrency: int,
        server_ids: list[int] | None = None,
        lite_quick: bool = True,
        worker_key: str = "default",
        lease_seconds: int = 180,
        *,
        rollup_interval: int = 3600,
        cert_interval: int = 21600,
        ai_interval: int = 21600,
    ) -> dict:
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
        rollup_counter = 0
        rollup_every_n = max(1, rollup_interval // quick_interval)
        cert_counter = 0
        cert_every_n = max(1, cert_interval // quick_interval)
        ai_counter = 0
        ai_every_n = max(1, ai_interval // quick_interval)
        # Duty briefings: check about once per hour of monitor cycles
        briefing_counter = 0
        briefing_every_n = max(1, 3600 // max(1, quick_interval))
        summary = {"cycle": 0, "mode": "", "checked": 0, "errors": 0, "cleanup_errors": 0}

        while not stop.is_set():
            quick_counter += 1
            cleanup_counter += 1
            is_deep = quick_counter % deep_every_n == 0

            try:
                check_type = "deep" if is_deep else ("lite" if lite_quick else "quick")
                logger.info("Monitor: starting {} check (cycle {})", check_type, quick_counter)
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    STUDIO_MONITOR_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"cycle": quick_counter, "mode": check_type},
                    cycle_started=True,
                )
                results = await check_all_servers(
                    deep=is_deep,
                    lite=lite_quick and not is_deep,
                    concurrency=concurrency,
                    server_ids=server_ids,
                )
                summary = {
                    "cycle": quick_counter,
                    "mode": check_type,
                    "checked": len(results),
                    "errors": summary["errors"],
                    "cleanup_errors": summary["cleanup_errors"],
                }
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    STUDIO_MONITOR_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary,
                    cycle_finished=True,
                )
                logger.info("Monitor: {} check done, {} servers checked", check_type, len(results))
            except Exception as exc:
                summary["errors"] += 1
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    STUDIO_MONITOR_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"last_error": str(exc)[:300]},
                    cycle_finished=True,
                )
                logger.error("Monitor: check cycle failed: {}", exc)

            if cleanup_counter >= cleanup_every_n:
                cleanup_counter = 0
                try:
                    await cleanup_old_data(days=7)
                except Exception as exc:
                    summary["cleanup_errors"] += 1
                    logger.error("Monitor: cleanup failed: {}", exc)

            rollup_counter += 1
            # First cycle bootstraps rollups/certs so a fresh install sees data immediately.
            if rollup_counter >= rollup_every_n or quick_counter == 1:
                rollup_counter = 0
                try:
                    rollup_summary = await sync_to_async(run_metric_rollups, thread_sensitive=True)()
                    logger.info(
                        "Monitor: metric rollups updated ({} hour, {} day)",
                        rollup_summary["hour_rows"],
                        rollup_summary["day_rows"],
                    )
                except Exception as exc:
                    logger.error("Monitor: metric rollup failed: {}", exc)
                try:
                    forecast_summary = await sync_to_async(run_forecast_persistence, thread_sensitive=True)(server_ids)
                    logger.info(
                        "Monitor: forecasts persisted ({} servers, {} predictions, +{}/-{} alerts)",
                        forecast_summary["servers"],
                        forecast_summary["predictions"],
                        forecast_summary["alerts_created"],
                        forecast_summary["alerts_resolved"],
                    )
                except Exception as exc:
                    logger.error("Monitor: forecast persistence failed: {}", exc)

            cert_counter += 1
            if cert_counter >= cert_every_n or quick_counter == 1:
                cert_counter = 0
                try:
                    cert_summary = await collect_certificates_for_all(concurrency=concurrency, server_ids=server_ids)
                    logger.info(
                        "Monitor: certificate scan done ({} of {} servers, {} certs)",
                        cert_summary.get("scanned", 0),
                        cert_summary.get("servers", 0),
                        cert_summary.get("certificates", 0),
                    )
                except Exception as exc:
                    logger.error("Monitor: certificate scan failed: {}", exc)

            briefing_counter += 1
            if briefing_counter >= briefing_every_n:
                briefing_counter = 0
                try:
                    from core_ui.services.operator_duty import deliver_briefings_for_all_users

                    briefing_summary = await sync_to_async(deliver_briefings_for_all_users, thread_sensitive=True)(
                        force=False
                    )
                    if briefing_summary.get("delivered"):
                        logger.info("Monitor: operator duty briefings {}", briefing_summary)
                except Exception as exc:
                    logger.error("Monitor: operator duty briefing failed: {}", exc)

            ai_counter += 1
            # No first-cycle bootstrap: LLM passes are costly, wait for history.
            if ai_counter >= ai_every_n:
                ai_counter = 0
                try:
                    ai_summary = await sync_to_async(run_ai_insights_for_servers, thread_sensitive=True)(server_ids)
                    if ai_summary.get("enabled"):
                        logger.info(
                            "Monitor: AI insights pass done (analyzed {}, reused {}, errors {})",
                            ai_summary.get("analyzed", 0),
                            ai_summary.get("reused", 0),
                            ai_summary.get("errors", 0),
                        )
                except Exception as exc:
                    logger.error("Monitor: AI insights pass failed: {}", exc)

            try:
                await asyncio.wait_for(stop.wait(), timeout=quick_interval)
                break
            except TimeoutError:
                pass

        logger.info("Monitor: graceful shutdown complete")
        return summary
