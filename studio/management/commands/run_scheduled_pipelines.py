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
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from app.background_workers import STUDIO_SCHEDULED_PIPELINES_WORKER
from app.runtime_limits import get_pipeline_run_limit_error
from app.worker_state import claim_background_worker, heartbeat_background_worker, stop_background_worker
from studio import cron_schedule
from studio.models import PipelineTrigger
from studio.ops_controls import assert_schedulers_not_paused
from studio.pipeline_runtime_context import validate_pipeline_entry_branch, validate_pipeline_runtime_context
from studio.pipeline_validation import validate_pipeline_definition

croniter = cron_schedule.croniter
_IMPORTED_CRONITER = croniter


def _croniter_factory():
    if croniter is not _IMPORTED_CRONITER:
        return croniter
    return cron_schedule.croniter


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
        parser.add_argument("--lease-seconds", type=int, default=180, help="Worker heartbeat lease duration")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")

    def handle(self, *args, **options):
        interval = options["interval"]
        daemon = options["daemon"]
        once = options["once"]
        lease_seconds = max(30, int(options.get("lease_seconds") or 180))
        worker_key = str(options.get("worker_key") or "default").strip() or "default"

        state = claim_background_worker(
            STUDIO_SCHEDULED_PIPELINES_WORKER,
            worker_key=worker_key,
            command="python manage.py run_scheduled_pipelines",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Pipeline scheduler worker {worker_key!r} is already leased by another process"))
            return

        self.stdout.write("Starting pipeline scheduler...")
        summary = {}
        try:
            if once or not daemon:
                summary = self._tick(interval, worker_key=worker_key, lease_seconds=lease_seconds)
            else:
                while True:
                    summary = self._tick(interval, worker_key=worker_key, lease_seconds=lease_seconds)
                    self.stdout.write(f"Next check in {interval}s...")
                    time.sleep(interval)
        finally:
            stop_background_worker(STUDIO_SCHEDULED_PIPELINES_WORKER, worker_key=worker_key, summary=summary)

    def _tick(self, interval_seconds: int = 60, *, worker_key: str = "default", lease_seconds: int = 180) -> dict:
        heartbeat_background_worker(
            STUDIO_SCHEDULED_PIPELINES_WORKER,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            cycle_started=True,
        )
        summary = {"evaluated": 0, "fired": 0, "skipped": 0, "errors": 0}
        paused = assert_schedulers_not_paused()
        if paused:
            self.stdout.write(self.style.WARNING(paused))
            summary["skipped"] += 1
            summary["paused"] = True
            return summary
        now = timezone.now()
        window_start = now - timedelta(seconds=max(interval_seconds, 60))
        triggers = PipelineTrigger.objects.select_related("pipeline").filter(
            trigger_type=PipelineTrigger.TYPE_SCHEDULE,
            is_active=True,
        )
        for trigger in triggers:
            if not trigger.cron_expression:
                summary["skipped"] += 1
                continue
            try:
                summary["evaluated"] += 1
                last_due_dt = cron_schedule.previous_due_datetime(
                    trigger.cron_expression,
                    now,
                    croniter_factory=_croniter_factory(),
                )

                if trigger.last_triggered_at:
                    should_fire = last_due_dt > trigger.last_triggered_at
                else:
                    should_fire = window_start <= last_due_dt <= now

                if should_fire:
                    result = self._fire_trigger(trigger)
                    summary["fired" if result == "fired" else "skipped"] += 1
            except Exception as exc:
                summary["errors"] += 1
                self.stderr.write(f"Error evaluating trigger #{trigger.pk}: {exc}")
        heartbeat_background_worker(
            STUDIO_SCHEDULED_PIPELINES_WORKER,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            summary=summary,
            cycle_finished=True,
        )
        return summary

    def _fire_trigger(self, trigger: PipelineTrigger) -> str:
        from studio.trigger_dispatch import (
            create_pipeline_run,
            launch_pipeline_run_async,
            pipeline_run_creation_error_details,
        )

        limit_error = get_pipeline_run_limit_error(trigger.pipeline.owner)
        if limit_error:
            self.stderr.write(
                f"Skipped trigger #{trigger.pk} ({trigger.pipeline.name}): {limit_error['error']}"
            )
            return "skipped"

        validation_errors = validate_pipeline_definition(
            nodes=trigger.pipeline.nodes,
            edges=trigger.pipeline.edges,
            owner=trigger.pipeline.owner,
            graph_version=trigger.pipeline.graph_version,
        )
        if validation_errors:
            self.stderr.write(
                f"Skipped trigger #{trigger.pk} ({trigger.pipeline.name}): {'; '.join(validation_errors)}"
            )
            return "skipped"
        branch_errors = validate_pipeline_entry_branch(
            trigger.pipeline.nodes,
            trigger.pipeline.edges,
            trigger.node_id,
        )
        if branch_errors:
            self.stderr.write(
                f"Skipped trigger #{trigger.pk} ({trigger.pipeline.name}): {'; '.join(branch_errors)}"
            )
            return "skipped"

        fired_at = timezone.now()
        context = {
            "trigger_source": "schedule",
            "cron": trigger.cron_expression,
            "scheduled_at": fired_at.isoformat(),
        }
        context_errors = validate_pipeline_runtime_context(
            trigger.pipeline.nodes,
            context,
            edges=trigger.pipeline.edges,
            entry_node_id=trigger.node_id,
        )
        if context_errors:
            self.stderr.write(
                f"Skipped trigger #{trigger.pk} ({trigger.pipeline.name}): {'; '.join(context_errors)}"
            )
            return "skipped"

        try:
            run = create_pipeline_run(
                pipeline=trigger.pipeline,
                trigger=trigger,
                context=context,
                trigger_data={"source": "schedule", "cron": trigger.cron_expression},
                entry_node_id=trigger.node_id,
            )
        except ValueError as exc:
            self.stderr.write(
                f"Skipped trigger #{trigger.pk} ({trigger.pipeline.name}): {'; '.join(pipeline_run_creation_error_details(exc))}"
            )
            return "skipped"
        trigger.last_triggered_at = fired_at
        trigger.save(update_fields=["last_triggered_at"])
        launch_pipeline_run_async(run)
        self.stdout.write(f"Fired trigger #{trigger.pk} ({trigger.pipeline.name}) → run #{run.pk}")
        return "fired"
