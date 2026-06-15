from __future__ import annotations

import asyncio
import time

from django.core.management.base import BaseCommand

from servers.worker_state import (
    claim_background_worker,
    heartbeat_background_worker,
    stop_background_worker,
)


class Command(BaseCommand):
    help = "Run the MARS queued-run worker."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds.")
        parser.add_argument("--once", action="store_true", help="Process at most one queued run and exit.")
        parser.add_argument("--worker-key", default="default", help="Worker lease key.")

    def handle(self, *args, **options):
        interval = max(float(options["interval"]), 0.2)
        once = bool(options["once"])
        worker_key = str(options["worker_key"] or "default")

        claimed = claim_background_worker(
            "mars",
            worker_key=worker_key,
            command="python manage.py run_mars_worker",
            lease_seconds=180,
        )
        if claimed is None:
            self.stderr.write("Another MARS worker holds the active lease.")
            return

        self.stdout.write("MARS worker started.")
        processed = 0
        try:
            while True:
                heartbeat_background_worker(
                    "mars",
                    worker_key=worker_key,
                    lease_seconds=180,
                    summary={"processed": processed},
                    cycle_started=True,
                )
                try:
                    run = asyncio.run(self._tick())
                except Exception as exc:
                    self.stderr.write(f"MARS worker tick failed: {exc}")
                    heartbeat_background_worker(
                        "mars",
                        worker_key=worker_key,
                        lease_seconds=180,
                        summary={"processed": processed, "last_error": str(exc)[:500]},
                        cycle_finished=True,
                    )
                    if once:
                        raise
                else:
                    if run is not None:
                        processed += 1
                        self.stdout.write(f"Processed MARS run #{run.id}")
                    heartbeat_background_worker(
                        "mars",
                        worker_key=worker_key,
                        lease_seconds=180,
                        summary={"processed": processed, "last_run_id": getattr(run, "id", None)},
                        cycle_finished=True,
                    )
                    if once:
                        break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("MARS worker stopped.")
        except Exception as exc:
            stop_background_worker("mars", worker_key=worker_key, summary={"processed": processed}, error=str(exc))
            raise
        else:
            stop_background_worker("mars", worker_key=worker_key, summary={"processed": processed})

    async def _tick(self):
        from mars.worker import execute_next_queued_run

        return await execute_next_queued_run()
