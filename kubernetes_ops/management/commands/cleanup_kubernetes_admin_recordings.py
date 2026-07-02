from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from kubernetes_ops.services.admin_recording import cleanup_interactive_recordings, recording_retention_inventory


class Command(BaseCommand):
    help = "Apply retention cleanup for Kubernetes Admin Mode recording evidence."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Delete expired recording evidence. Defaults to dry-run.")
        parser.add_argument("--batch-size", type=int, default=1000, help="Delete batch size when --apply is used.")
        parser.add_argument("--inventory", action="store_true", help="Only print retention inventory and ignore --apply.")

    def handle(self, *args, **options):
        try:
            if bool(options.get("inventory")):
                inventory = recording_retention_inventory()
                summary = inventory["summary"]
                self.stdout.write(
                    "Kubernetes admin recording retention inventory "
                    f"metadata_expired={summary['metadata_expired_count']} "
                    f"transcript_expired={summary['transcript_expired_count']} "
                    f"transcript_events_expired={summary['transcript_event_expired_count']} "
                    f"total_recordings={summary['total_recording_count']} "
                    f"total_events={summary['total_event_count']}"
                )
                return
            result = cleanup_interactive_recordings(
                dry_run=not bool(options.get("apply")),
                batch_size=int(options.get("batch_size") or 1000),
            )
        except (OperationalError, ProgrammingError) as exc:
            raise CommandError("Kubernetes Admin Mode recording tables are not ready. Run `python manage.py migrate kubernetes_ops`.") from exc

        self.stdout.write(
            "Kubernetes admin recording retention "
            f"dry_run={result['dry_run']} "
            f"metadata_expired={result['metadata_expired_count']} "
            f"metadata_deleted={result['metadata_deleted_count']} "
            f"transcript_expired={result['transcript_expired_count']} "
            f"transcript_events_deleted={result['transcript_event_deleted_count']} "
            f"active_recordings={result['active_recording_count']} "
            f"active_events={result['active_event_count']}"
        )
        for row in result["metadata_expired_by_operation"]:
            self.stdout.write(f"  metadata expired operation={row['operation']} count={row['count']}")
        for row in result["transcript_expired_by_operation"]:
            self.stdout.write(f"  transcript expired operation={row['operation']} count={row['count']}")
        if result["dry_run"] and (result["metadata_expired_count"] or result["transcript_expired_count"]):
            self.stdout.write(self.style.WARNING("Dry run only. Re-run with --apply to delete expired Kubernetes admin recording evidence."))
        elif not result["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Kubernetes admin recording retention cleanup applied."))
