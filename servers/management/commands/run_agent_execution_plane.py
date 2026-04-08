from __future__ import annotations

import asyncio
import signal
import sys

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from loguru import logger

from servers.agent_background import execute_agent_dispatch
from servers.agent_dispatch import claim_next_agent_dispatch
from servers.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker


class Command(BaseCommand):
    help = "Run the dedicated execution-plane worker for queued full/multi agent runs."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds while the queue is empty")
        parser.add_argument("--lease-seconds", type=int, default=180, help="Heartbeat lease duration for worker and claimed dispatches")
        parser.add_argument("--limit", type=int, default=100, help="Maximum dispatches to process per cycle in once mode")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")
        parser.add_argument("--once", action="store_true", help="Process queued dispatches once and exit")

    def handle(self, *args, **options):
        interval = max(2, int(options["interval"]))
        lease_seconds = max(30, int(options["lease_seconds"]))
        limit = max(1, min(int(options["limit"]), 500))
        worker_key = str(options["worker_key"] or "default").strip() or "default"
        once = bool(options["once"])

        state = claim_background_worker(
            "agent_execution",
            worker_key=worker_key,
            command="python manage.py run_agent_execution_plane",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Execution worker {worker_key!r} is already leased by another process"))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting agent execution plane worker ({worker_key})"))
        last_summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0}
        try:
            if once:
                last_summary = self._run_once(worker_key=worker_key, lease_seconds=lease_seconds, limit=limit)
                self.stdout.write(self.style.SUCCESS(self._format_summary(last_summary)))
                return

            asyncio.run(self._run_loop(worker_key=worker_key, lease_seconds=lease_seconds, interval=interval))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nExecution worker stopped by user"))
        finally:
            stop_background_worker("agent_execution", worker_key=worker_key, summary=last_summary)

    def _run_once(self, *, worker_key: str, lease_seconds: int, limit: int) -> dict:
        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0}
        for _index in range(limit):
            heartbeat_background_worker(
                "agent_execution",
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                cycle_started=True,
            )
            dispatch = claim_next_agent_dispatch(worker_name=worker_key, lease_seconds=lease_seconds)
            if dispatch is None:
                summary["empty_polls"] += 1
                heartbeat_background_worker(
                    "agent_execution",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary,
                    cycle_finished=True,
                )
                break

            try:
                asyncio.run(execute_agent_dispatch(dispatch.id, worker_key=worker_key, lease_seconds=lease_seconds))
                summary["completed"] += 1
            except Exception as exc:
                logger.exception("Execution-plane dispatch {} failed: {}", dispatch.id, exc)
                summary["failed"] += 1
            finally:
                summary["processed"] += 1
                heartbeat_background_worker(
                    "agent_execution",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"last_dispatch_id": dispatch.id},
                    cycle_finished=True,
                )
        return summary

    async def _run_loop(self, *, worker_key: str, lease_seconds: int, interval: int):
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig and sys.platform != "win32":
                loop.add_signal_handler(sig, stop.set)

        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0}
        cycle = 0
        while not stop.is_set():
            cycle += 1
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                "agent_execution",
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                cycle_started=True,
            )
            dispatch = await sync_to_async(claim_next_agent_dispatch, thread_sensitive=True)(
                worker_name=worker_key,
                lease_seconds=lease_seconds,
            )
            if dispatch is None:
                summary["empty_polls"] += 1
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    "agent_execution",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary,
                    cycle_finished=True,
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                    break
                except asyncio.TimeoutError:
                    continue

            try:
                await execute_agent_dispatch(dispatch.id, worker_key=worker_key, lease_seconds=lease_seconds)
                summary["completed"] += 1
            except Exception as exc:
                logger.exception("Execution-plane dispatch {} failed: {}", dispatch.id, exc)
                summary["failed"] += 1
            finally:
                summary["processed"] += 1
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    "agent_execution",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"last_dispatch_id": dispatch.id, "cycle": cycle},
                    cycle_finished=True,
                )

    @staticmethod
    def _format_summary(summary: dict) -> str:
        return (
            f"processed={summary.get('processed', 0)} "
            f"completed={summary.get('completed', 0)} "
            f"failed={summary.get('failed', 0)} "
            f"empty_polls={summary.get('empty_polls', 0)}"
        )
