from __future__ import annotations

import asyncio
import signal
import socket
import sys

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from loguru import logger

from app.runtime_limits import cleanup_stale_agent_runs
from servers.agents.agent_background import execute_agent_dispatch
from servers.agents.agent_dispatch import claim_next_agent_dispatch
from servers.worker_state import (
    claim_background_worker,
    cleanup_stale_background_workers,
    heartbeat_background_worker,
    stop_background_worker,
)


class Command(BaseCommand):
    help = "Run the dedicated execution-plane worker for queued mini/full/multi agent runs."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds while the queue is empty")
        parser.add_argument(
            "--lease-seconds", type=int, default=180, help="Heartbeat lease duration for worker and claimed dispatches"
        )
        parser.add_argument(
            "--global-concurrency",
            type=int,
            default=None,
            help="Database-enforced maximum active agent dispatches across every replica",
        )
        parser.add_argument(
            "--per-user-concurrency",
            type=int,
            default=None,
            help="Database-enforced maximum active dispatches owned by one user",
        )
        parser.add_argument(
            "--worker-concurrency",
            type=int,
            default=None,
            help="Maximum dispatches executed concurrently inside this worker process",
        )
        parser.add_argument(
            "--limit", type=int, default=100, help="Maximum dispatches to process per cycle in once mode"
        )
        parser.add_argument("--worker-key", type=str, default="", help="Unique worker key; defaults to hostname")
        parser.add_argument("--once", action="store_true", help="Process queued dispatches once and exit")

    def handle(self, *args, **options):
        interval = max(2, int(options["interval"]))
        lease_seconds = max(30, int(options["lease_seconds"]))
        limit = max(1, min(int(options["limit"]), 500))
        worker_key = str(options["worker_key"] or socket.gethostname()).strip() or socket.gethostname()
        global_concurrency = max(
            1,
            int(options.get("global_concurrency") or getattr(settings, "AGENT_EXECUTION_GLOBAL_CONCURRENCY", 10)),
        )
        per_user_concurrency = max(
            1,
            int(options.get("per_user_concurrency") or getattr(settings, "AGENT_EXECUTION_PER_USER_CONCURRENCY", 2)),
        )
        worker_concurrency = max(
            1,
            min(
                int(options.get("worker_concurrency") or getattr(settings, "AGENT_EXECUTION_WORKER_CONCURRENCY", 1)),
                32,
            ),
        )
        once = bool(options["once"])

        cleanup_stale_background_workers("agent_execution")
        state = claim_background_worker(
            "agent_execution",
            worker_key=worker_key,
            command=(
                "python manage.py run_agent_execution_plane "
                f"--worker-key {worker_key} --worker-concurrency {worker_concurrency}"
            ),
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(
                self.style.WARNING(f"Execution worker {worker_key!r} is already leased by another process")
            )
            return

        self.stdout.write(self.style.SUCCESS(f"Starting agent execution plane worker ({worker_key})"))
        last_summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0, "stale_cleaned": 0}
        fatal_error = ""
        try:
            if once:
                last_summary = self._run_once(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    limit=limit,
                    global_concurrency=global_concurrency,
                    per_user_concurrency=per_user_concurrency,
                )
                self.stdout.write(self.style.SUCCESS(self._format_summary(last_summary)))
                if int(last_summary.get("failed") or 0) > 0:
                    raise CommandError(f"Execution plane dispatches failed: {last_summary['failed']}")
                return

            last_summary = asyncio.run(
                self._run_loop(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    interval=interval,
                    global_concurrency=global_concurrency,
                    per_user_concurrency=per_user_concurrency,
                    worker_concurrency=worker_concurrency,
                )
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nExecution worker stopped by user"))
        except CommandError:
            raise
        except Exception as exc:
            fatal_error = f"{exc.__class__.__name__}: {exc}"
            logger.exception("Execution plane worker crashed: {}", exc)
            raise
        finally:
            stop_background_worker("agent_execution", worker_key=worker_key, summary=last_summary, error=fatal_error)

    def _run_once(
        self,
        *,
        worker_key: str,
        lease_seconds: int,
        limit: int,
        global_concurrency: int,
        per_user_concurrency: int,
    ) -> dict:
        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0, "stale_cleaned": 0}
        for _index in range(limit):
            summary["stale_cleaned"] += cleanup_stale_agent_runs()
            heartbeat_background_worker(
                "agent_execution",
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                cycle_started=True,
            )
            dispatch = claim_next_agent_dispatch(
                worker_name=worker_key,
                lease_seconds=lease_seconds,
                global_concurrency=global_concurrency,
                per_user_concurrency=per_user_concurrency,
            )
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

    async def _run_loop(
        self,
        *,
        worker_key: str,
        lease_seconds: int,
        interval: int,
        global_concurrency: int,
        per_user_concurrency: int,
        worker_concurrency: int,
    ):
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig and sys.platform != "win32":
                loop.add_signal_handler(sig, stop.set)

        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0, "stale_cleaned": 0}
        cycle = 0
        active_tasks: dict[asyncio.Task[bool], int] = {}
        while not stop.is_set() or active_tasks:
            cycle += 1
            if not stop.is_set():
                summary["stale_cleaned"] += await sync_to_async(cleanup_stale_agent_runs, thread_sensitive=True)()
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    "agent_execution",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"active_dispatches": len(active_tasks)},
                    cycle_started=True,
                )

                while len(active_tasks) < worker_concurrency and not stop.is_set():
                    dispatch = await sync_to_async(claim_next_agent_dispatch, thread_sensitive=True)(
                        worker_name=worker_key,
                        lease_seconds=lease_seconds,
                        global_concurrency=global_concurrency,
                        per_user_concurrency=per_user_concurrency,
                    )
                    if dispatch is None:
                        break
                    task = asyncio.create_task(
                        self._execute_dispatch(
                            dispatch.id,
                            worker_key=worker_key,
                            lease_seconds=lease_seconds,
                        ),
                        name=f"agent-dispatch-{dispatch.id}",
                    )
                    active_tasks[task] = dispatch.id

            if not active_tasks:
                if stop.is_set():
                    break
                summary["empty_polls"] += 1
                await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                    "agent_execution",
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"active_dispatches": 0},
                    cycle_finished=True,
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=interval)
                    break
                except TimeoutError:
                    continue

            done, _pending = await asyncio.wait(
                active_tasks,
                timeout=interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                dispatch_id = active_tasks.pop(task)
                summary["processed"] += 1
                if task.result():
                    summary["completed"] += 1
                else:
                    summary["failed"] += 1
                summary["last_dispatch_id"] = dispatch_id

            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                "agent_execution",
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                summary=summary | {"active_dispatches": len(active_tasks), "cycle": cycle},
                cycle_finished=bool(done),
            )

        return summary

    @staticmethod
    async def _execute_dispatch(dispatch_id: int, *, worker_key: str, lease_seconds: int) -> bool:
        try:
            await execute_agent_dispatch(dispatch_id, worker_key=worker_key, lease_seconds=lease_seconds)
            return True
        except Exception as exc:
            logger.exception("Execution-plane dispatch {} failed: {}", dispatch_id, exc)
            return False

    @staticmethod
    def _format_summary(summary: dict) -> str:
        return (
            f"processed={summary.get('processed', 0)} "
            f"completed={summary.get('completed', 0)} "
            f"failed={summary.get('failed', 0)} "
            f"empty_polls={summary.get('empty_polls', 0)} "
            f"stale_cleaned={summary.get('stale_cleaned', 0)}"
        )
