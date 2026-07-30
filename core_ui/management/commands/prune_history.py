from __future__ import annotations

import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from core_ui.history_retention import prune_history


class Command(BaseCommand):
    help = "Prune high-volume history tables in bounded batches outside HTTP request handling."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=1000)
        parser.add_argument("--daemon", action="store_true")
        parser.add_argument("--interval-seconds", type=int, default=86400)

    def _run_once(self, *, dry_run: bool, batch_size: int) -> None:
        report = prune_history(dry_run=dry_run, batch_size=batch_size)
        for name, result in report.items():
            self.stdout.write(
                f"{name}: deleted={result['deleted']} age_candidates={result['age_candidates']} "
                f"overflow_candidates={result['overflow_candidates']} max_age_days={result['max_age_days']} "
                f"max_rows={result['max_rows']}"
            )

    def handle(self, *args, **options):
        batch_size = int(options["batch_size"] or 0)
        if batch_size < 1 or batch_size > 10_000:
            raise CommandError("--batch-size must be between 1 and 10000")

        interval_seconds = int(options["interval_seconds"] or 0)
        if options["daemon"] and not 60 <= interval_seconds <= 604_800:
            raise CommandError("--interval-seconds must be between 60 and 604800")

        if not options["daemon"]:
            self._run_once(dry_run=bool(options["dry_run"]), batch_size=batch_size)
            return

        stopped = threading.Event()

        def request_stop(_signum, _frame) -> None:
            stopped.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        while not stopped.is_set():
            self._run_once(dry_run=bool(options["dry_run"]), batch_size=batch_size)
            stopped.wait(interval_seconds)
