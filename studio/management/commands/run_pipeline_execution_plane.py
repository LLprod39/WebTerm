from __future__ import annotations

import asyncio
import signal
import sys

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from loguru import logger

from app.background_workers import STUDIO_PIPELINE_EXECUTION_WORKER
from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from studio.dispatch import claim_next_pipeline_dispatch, execute_pipeline_dispatch


class Command(BaseCommand):
    help = "Run the durable execution-plane worker for queued Studio pipeline runs."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5, help="Queue poll interval in seconds")
        parser.add_argument("--lease-seconds", type=int, default=180, help="Dispatch and worker lease duration")
        parser.add_argument("--limit", type=int, default=100, help="Maximum dispatches in --once mode")
        parser.add_argument("--global-concurrency", type=int, default=4, help="Global active dispatch limit")
        parser.add_argument("--per-user-concurrency", type=int, default=2, help="Active dispatch limit per owner")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")
        parser.add_argument("--once", action="store_true", help="Drain currently available work and exit")

    def handle(self, *args, **options):
        interval = max(1, int(options["interval"]))
        lease_seconds = max(30, int(options["lease_seconds"]))
        limit = max(1, min(500, int(options["limit"])))
        global_concurrency = max(1, int(options["global_concurrency"]))
        per_user_concurrency = max(1, int(options["per_user_concurrency"]))
        worker_key = str(options["worker_key"] or "default").strip()[:120] or "default"
        once = bool(options["once"])

        state = claim_background_worker(
            STUDIO_PIPELINE_EXECUTION_WORKER,
            worker_key=worker_key,
            command=f"python manage.py run_pipeline_execution_plane --worker-key {worker_key}",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Pipeline worker {worker_key!r} is already leased"))
            return

        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0}
        fatal_error = ""
        try:
            if once:
                summary = asyncio.run(
                    self._drain_once(
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        limit=limit,
                        global_concurrency=global_concurrency,
                        per_user_concurrency=per_user_concurrency,
                    )
                )
                self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
                if summary["failed"]:
                    raise CommandError(f"Pipeline execution dispatches failed: {summary['failed']}")
                return
            asyncio.run(
                self._run_loop(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    interval=interval,
                    global_concurrency=global_concurrency,
                    per_user_concurrency=per_user_concurrency,
                    summary=summary,
                )
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Pipeline execution worker stopped"))
        except CommandError:
            raise
        except Exception as exc:
            fatal_error = f"{exc.__class__.__name__}: {exc}"
            logger.exception("Pipeline execution worker crashed: {}", exc)
            raise
        finally:
            stop_background_worker(
                STUDIO_PIPELINE_EXECUTION_WORKER,
                worker_key=worker_key,
                summary=summary,
                error=fatal_error,
            )

    async def _drain_once(
        self,
        *,
        worker_key: str,
        lease_seconds: int,
        limit: int,
        global_concurrency: int,
        per_user_concurrency: int,
    ) -> dict[str, int]:
        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0}
        for _index in range(limit):
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                STUDIO_PIPELINE_EXECUTION_WORKER,
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                cycle_started=True,
            )
            dispatch = await sync_to_async(claim_next_pipeline_dispatch, thread_sensitive=True)(
                worker_name=worker_key,
                lease_seconds=lease_seconds,
                global_concurrency=global_concurrency,
                per_user_concurrency=per_user_concurrency,
            )
            if dispatch is None:
                summary["empty_polls"] += 1
                break
            try:
                await execute_pipeline_dispatch(dispatch.pk, worker_name=worker_key, lease_seconds=lease_seconds)
                summary["completed"] += 1
            except Exception as exc:
                logger.exception("Pipeline dispatch {} failed: {}", dispatch.pk, exc)
                summary["failed"] += 1
            finally:
                summary["processed"] += 1
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    STUDIO_PIPELINE_EXECUTION_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"last_dispatch_id": dispatch.pk},
                    cycle_finished=True,
                )
        return summary

    async def _run_loop(
        self,
        *,
        worker_key: str,
        lease_seconds: int,
        interval: int,
        global_concurrency: int,
        per_user_concurrency: int,
        summary: dict[str, int],
    ) -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signal_name in ("SIGINT", "SIGTERM"):
            current_signal = getattr(signal, signal_name, None)
            if current_signal and sys.platform != "win32":
                loop.add_signal_handler(current_signal, stop.set)

        while not stop.is_set():
            cycle_summary = await self._drain_once(
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                limit=1,
                global_concurrency=global_concurrency,
                per_user_concurrency=per_user_concurrency,
            )
            for key in summary:
                summary[key] += cycle_summary[key]
            if cycle_summary["processed"]:
                continue
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    @staticmethod
    def _format_summary(summary: dict[str, int]) -> str:
        return " ".join(f"{key}={value}" for key, value in summary.items())
