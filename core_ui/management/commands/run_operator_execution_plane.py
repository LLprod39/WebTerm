from __future__ import annotations

import asyncio

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from loguru import logger

from app.background_workers import OPERATOR_TURN_EXECUTION_WORKER
from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from core_ui.services.operator_dispatch import claim_next_operator_dispatch, execute_operator_dispatch


class Command(BaseCommand):
    help = "Run the durable execution-plane worker for queued Operator Chat turns."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=2)
        parser.add_argument("--lease-seconds", type=int, default=180)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--worker-key", type=str, default="default")
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        interval = max(1, int(options["interval"]))
        lease_seconds = max(30, int(options["lease_seconds"]))
        limit = max(1, min(500, int(options["limit"])))
        worker_key = str(options["worker_key"] or "default").strip()[:120] or "default"
        state = claim_background_worker(
            OPERATOR_TURN_EXECUTION_WORKER,
            worker_key=worker_key,
            command=f"python manage.py run_operator_execution_plane --worker-key {worker_key}",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Operator worker {worker_key!r} is already leased"))
            return
        summary = {"processed": 0, "completed": 0, "failed": 0, "empty_polls": 0}
        fatal_error = ""
        try:
            asyncio.run(
                self._run(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    interval=interval,
                    limit=limit,
                    once=bool(options["once"]),
                    summary=summary,
                )
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Operator execution worker stopped"))
        except Exception as exc:
            fatal_error = f"{exc.__class__.__name__}: {exc}"
            logger.exception("Operator execution worker crashed: {}", exc)
            raise CommandError(fatal_error) from exc
        finally:
            stop_background_worker(
                OPERATOR_TURN_EXECUTION_WORKER,
                worker_key=worker_key,
                summary=summary,
                error=fatal_error,
            )
        self.stdout.write(self.style.SUCCESS(f"Operator dispatch summary: {summary}"))

    async def _run(self, *, worker_key, lease_seconds, interval, limit, once, summary):
        while True:
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                OPERATOR_TURN_EXECUTION_WORKER,
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                summary=summary,
                cycle_started=True,
            )
            dispatch = await sync_to_async(claim_next_operator_dispatch, thread_sensitive=True)(
                worker_name=worker_key,
                lease_seconds=lease_seconds,
            )
            if dispatch is None:
                summary["empty_polls"] += 1
                if once:
                    return
                await asyncio.sleep(interval)
                continue
            try:
                status = await execute_operator_dispatch(
                    dispatch.pk,
                    worker_name=worker_key,
                    lease_seconds=lease_seconds,
                )
                summary["completed" if status in {"completed", "canceled"} else "failed"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Operator dispatch {} failed: {}", dispatch.pk, exc)
                summary["failed"] += 1
            summary["processed"] += 1
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                OPERATOR_TURN_EXECUTION_WORKER,
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                summary=summary,
                cycle_finished=True,
            )
            if once and summary["processed"] >= limit:
                return
