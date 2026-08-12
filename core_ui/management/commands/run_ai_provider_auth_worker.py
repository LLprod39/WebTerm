from __future__ import annotations

import asyncio
import os
import socket
import uuid

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from loguru import logger

from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from core_ui.services.ai_provider_auth import (
    claim_next_auth_flow,
    retry_pending_credential_cleanup,
    run_claimed_auth_flow,
)
from servers.models import BackgroundWorkerState

WORKER_KIND = BackgroundWorkerState.KIND_AI_PROVIDER_AUTH


class Command(BaseCommand):
    help = "Run durable device-code authentication flows for subscription CLI providers."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=2)
        parser.add_argument("--worker-key", type=str, default="")
        parser.add_argument("--concurrency", type=int, default=2)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        worker_key = str(
            options.get("worker_key")
            or f"{socket.gethostname() or 'auth-worker'}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        )[:80]
        concurrency = max(1, min(int(options.get("concurrency") or 2), 8))
        claimed = claim_background_worker(
            WORKER_KIND,
            worker_key=worker_key,
            command=f"python manage.py run_ai_provider_auth_worker --worker-key {worker_key}",
            lease_seconds=90,
        )
        if claimed is None:
            raise CommandError(f"AI provider auth worker '{worker_key}' is already active")
        summary = {
            "processed": 0,
            "failed": 0,
            "cleanup_completed": 0,
            "active": 0,
            "concurrency": concurrency,
        }
        error = ""
        try:
            asyncio.run(
                self._run(
                    worker_key=worker_key,
                    interval=max(1, int(options["interval"])),
                    concurrency=concurrency,
                    once=bool(options["once"]),
                    summary=summary,
                )
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                asyncio.run(sync_to_async(connections.close_all, thread_sensitive=True)())
            finally:
                stop_background_worker(WORKER_KIND, worker_key=worker_key, summary=summary, error=error)

    async def _run(
        self,
        *,
        worker_key: str,
        interval: int,
        concurrency: int,
        once: bool,
        summary: dict[str, int],
    ) -> None:
        active: set[asyncio.Task[bool]] = set()
        claimed_any = False
        while True:
            summary["cleanup_completed"] += await sync_to_async(
                retry_pending_credential_cleanup, thread_sensitive=True
            )()
            while len(active) < concurrency:
                claim = await sync_to_async(claim_next_auth_flow, thread_sensitive=True)(worker_name=worker_key)
                if claim is None:
                    break
                flow_id, fencing_token = claim
                claimed_any = True
                active.add(
                    asyncio.create_task(
                        self._process_flow(
                            flow_id,
                            worker_name=worker_key,
                            fencing_token=fencing_token,
                        )
                    )
                )
            summary["active"] = len(active)
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                WORKER_KIND,
                worker_key=worker_key,
                lease_seconds=90,
                summary=summary,
                cycle_started=True,
            )
            if not active:
                if once:
                    return
                await asyncio.sleep(interval)
                continue
            done, active = await asyncio.wait(
                active,
                timeout=interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                if await task:
                    summary["processed"] += 1
                else:
                    summary["failed"] += 1
            summary["active"] = len(active)
            await sync_to_async(heartbeat_background_worker, thread_sensitive=True)(
                WORKER_KIND,
                worker_key=worker_key,
                lease_seconds=90,
                summary=summary,
                cycle_finished=bool(done),
            )
            if once and claimed_any and not active:
                return

    async def _process_flow(self, flow_id: int, *, worker_name: str, fencing_token: int) -> bool:
        try:
            await run_claimed_auth_flow(
                flow_id,
                worker_name=worker_name,
                fencing_token=fencing_token,
            )
            self.stdout.write(self.style.SUCCESS(f"Processed AI provider auth flow {flow_id}"))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI provider auth flow {} failed: {}", flow_id, exc)
            return False
