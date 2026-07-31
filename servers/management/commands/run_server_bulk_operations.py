from __future__ import annotations

import socket
import time

from django.core.management.base import BaseCommand
from loguru import logger

from servers.services.server_bulk_operations import claim_bulk_operation, process_bulk_operation


class Command(BaseCommand):
    help = "Run the durable worker for queued server-group bulk operations."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Drain currently available operations and exit")
        parser.add_argument("--interval", type=float, default=2.0, help="Queue poll interval in seconds")
        parser.add_argument("--lease-seconds", type=int, default=90, help="Operation lease duration")
        parser.add_argument("--limit", type=int, default=100, help="Maximum operations in --once mode")
        parser.add_argument("--worker-key", type=str, default="", help="Stable worker instance key")

    def handle(self, *args, **options):
        once = bool(options["once"])
        interval = max(float(options["interval"]), 0.2)
        lease_seconds = max(int(options["lease_seconds"]), 30)
        limit = max(1, min(int(options["limit"]), 1000))
        worker_key = str(options["worker_key"] or socket.gethostname() or "server-bulk-worker")[:160]
        processed = 0

        while True:
            operation = claim_bulk_operation(worker_id=worker_key, lease_seconds=lease_seconds)
            if operation is None:
                if once:
                    break
                time.sleep(interval)
                continue
            try:
                process_bulk_operation(operation, worker_id=worker_key, lease_seconds=lease_seconds)
                processed += 1
            except Exception as exc:
                # Leave the durable lease in place. Another worker can resume
                # from the persisted cursor after it expires.
                logger.exception("Server bulk operation {} failed: {}", operation.pk, exc)
                if once:
                    raise
                time.sleep(interval)
            if once and processed >= limit:
                break

        self.stdout.write(self.style.SUCCESS(f"processed={processed}"))
