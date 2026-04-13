"""
Management command: run_scheduled_pipelines

Polls PipelineTrigger records with trigger_type='schedule' and fires those
whose cron expression indicates it's time to run.

Usage:
    python manage.py run_scheduled_pipelines --interval 60

Run as a persistent daemon:
    python manage.py run_scheduled_pipelines --daemon
"""

import time
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

try:
    from croniter import croniter
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local mini env
    croniter = None

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.runtime_limits import get_pipeline_run_limit_error
from studio.models import PipelineTrigger


class Command(BaseCommand):
    help = "Poll and fire scheduled pipeline triggers"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Poll interval in seconds (default: 60)",
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Run continuously until interrupted",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run once and exit (for cron job wrappers)",
        )

    def handle(self, *args, **options):
        interval = options["interval"]
        daemon = options["daemon"]
        once = options["once"]

        self.stdout.write("Starting pipeline scheduler...")
        if once or not daemon:
            self._tick(interval)
        else:
            while True:
                self._tick(interval)
                self.stdout.write(f"Next check in {interval}s...")
                time.sleep(interval)

    def _tick(self, interval_seconds: int = 60):
        if croniter is None:
            self.stderr.write("croniter is not installed; schedule triggers are unavailable in this environment.")
            return
        now = timezone.now()
        window_start = now - timedelta(seconds=max(interval_seconds, 60))
        triggers = PipelineTrigger.objects.select_related("pipeline").filter(
            trigger_type=PipelineTrigger.TYPE_SCHEDULE,
            is_active=True,
        )
        for trigger in triggers:
            if not trigger.cron_expression:
                continue
            try:
                cron = croniter(trigger.cron_expression, now)
                last_due_ts = cron.get_prev(float)
                last_due_dt = datetime.fromtimestamp(last_due_ts, tz=dt_timezone.utc)
                if timezone.is_aware(now):
                    last_due_dt = last_due_dt.astimezone(now.tzinfo)

                if trigger.last_triggered_at:
                    should_fire = last_due_dt > trigger.last_triggered_at
                else:
                    should_fire = window_start <= last_due_dt <= now

                if should_fire:
                    self._fire_trigger(trigger)
            except Exception as exc:
                self.stderr.write(f"Error evaluating trigger #{trigger.pk}: {exc}")

    def _fire_trigger(self, trigger: PipelineTrigger):
        from studio.trigger_dispatch import create_pipeline_run, launch_pipeline_run_async

        limit_error = get_pipeline_run_limit_error(trigger.pipeline.owner)
        if limit_error:
            self.stderr.write(
                f"Skipped trigger #{trigger.pk} ({trigger.pipeline.name}): {limit_error['error']}"
            )
            return

        run = create_pipeline_run(
            pipeline=trigger.pipeline,
            trigger=trigger,
            trigger_data={"source": "schedule", "cron": trigger.cron_expression},
            entry_node_id=trigger.node_id,
        )
        trigger.last_triggered_at = timezone.now()
        trigger.save(update_fields=["last_triggered_at"])
        launch_pipeline_run_async(run)
        self.stdout.write(f"Fired trigger #{trigger.pk} ({trigger.pipeline.name}) → run #{run.pk}")
