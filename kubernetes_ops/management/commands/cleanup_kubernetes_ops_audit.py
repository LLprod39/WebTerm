from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from kubernetes_ops.services.audit_retention import cleanup_kubernetes_audit_events, configured_audit_retention_days


class Command(BaseCommand):
    help = "Apply retention cleanup for Kubernetes Ops audit events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Retention window in days. Defaults to KUBERNETES_OPS_AUDIT_RETENTION_DAYS.",
        )
        parser.add_argument("--apply", action="store_true", help="Delete expired audit events. Defaults to dry-run.")
        parser.add_argument("--batch-size", type=int, default=1000, help="Delete batch size when --apply is used.")

    def handle(self, *args, **options):
        retention_days = configured_audit_retention_days(
            options.get("days")
            if options.get("days") is not None
            else getattr(settings, "KUBERNETES_OPS_AUDIT_RETENTION_DAYS", None)
        )
        try:
            result = cleanup_kubernetes_audit_events(
                retention_days=retention_days,
                dry_run=not bool(options.get("apply")),
                batch_size=int(options.get("batch_size") or 1000),
            )
        except (OperationalError, ProgrammingError) as exc:
            raise CommandError(
                "Kubernetes Ops tables are not ready. Run `python manage.py migrate kubernetes_ops`."
            ) from exc

        self.stdout.write(
            "Kubernetes audit retention "
            f"dry_run={result['dry_run']} "
            f"retention_days={result['retention_days']} "
            f"expired={result['expired_count']} "
            f"deleted={result['deleted_count']} "
            f"retained={result['retained_count']}"
        )
        for row in result["expired_by_action"]:
            self.stdout.write(f"  expired action={row['action']} count={row['count']}")
        if result["dry_run"] and result["expired_count"]:
            self.stdout.write(
                self.style.WARNING("Dry run only. Re-run with --apply to delete expired Kubernetes audit events.")
            )
        elif not result["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Kubernetes audit retention cleanup applied."))
