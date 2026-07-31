from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from app.runtime_limit_config import get_runtime_limit_setting
from studio.pipeline_reconciliation import reconcile_stale_pipeline_runs


class Command(BaseCommand):
    help = "Fail pending/running pipeline runs that no longer have a live execution worker."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--stale-seconds",
            type=int,
            default=None,
            help="Override PIPELINE_RUN_STALE_SECONDS for this reconciliation.",
        )

    def handle(self, *args, **options):
        configured = options.get("stale_seconds")
        stale_seconds = (
            get_runtime_limit_setting("PIPELINE_RUN_STALE_SECONDS") if configured is None else int(configured)
        )
        if stale_seconds < 0:
            raise CommandError("--stale-seconds must be zero or greater")
        count = reconcile_stale_pipeline_runs(
            stale_seconds=stale_seconds,
            reason="worker_restart",
        )
        self.stdout.write(
            self.style.SUCCESS(f"Pipeline reconciliation complete: failed={count}, stale_seconds={stale_seconds}.")
        )
