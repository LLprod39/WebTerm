from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.readiness import build_studio_readiness_report


class Command(BaseCommand):
    help = "Check Studio pipeline readiness for production preflight."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User scope to check. Staff users see all pipelines; non-staff users see their own.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the full readiness report as JSON.",
        )
        parser.add_argument(
            "--pipeline-id",
            action="append",
            type=int,
            default=None,
            help="Limit the check to one pipeline id. Can be passed more than once.",
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Check only pipelines with at least one active trigger.",
        )
        parser.add_argument(
            "--entry-node-id",
            type=str,
            default="",
            help="Check readiness for a specific trigger branch within the selected pipeline scope.",
        )
        parser.add_argument(
            "--fail-on-warning",
            action="store_true",
            help="Return a non-zero exit code when readiness status is warning.",
        )
        parser.add_argument(
            "--no-fail",
            action="store_true",
            help="Always return zero; useful for diagnostics.",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        report = build_studio_readiness_report(
            user,
            pipeline_ids=options.get("pipeline_id"),
            active_only=bool(options.get("active_only")),
            entry_node_id=options.get("entry_node_id") or "",
        )

        if options.get("json"):
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            self._write_human_report(report, username=user.username)

        should_fail = report["status"] == "not_ready" or (
            bool(options.get("fail_on_warning")) and report["status"] == "warning"
        )
        if should_fail and not options.get("no_fail"):
            raise CommandError(f"Studio readiness status={report['status']}")

    def _resolve_user(self, username: str | None):
        user_model = get_user_model()
        if username:
            user = user_model.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"User '{username}' not found.")
            return user

        user = user_model.objects.filter(is_superuser=True).order_by("id").first()
        if user is not None:
            return user
        user = user_model.objects.filter(is_staff=True).order_by("id").first()
        if user is not None:
            return user
        user = user_model.objects.order_by("id").first()
        if user is not None:
            return user
        raise CommandError("No users found in the database.")

    def _write_human_report(self, report: dict, *, username: str) -> None:
        summary = report.get("summary") or {}
        status = report.get("status")
        style = self.style.SUCCESS if status == "ready" else self.style.WARNING
        if status == "not_ready":
            style = self.style.ERROR
        self.stdout.write(style(f"Studio readiness for {username}: status={status}"))
        scope = report.get("scope") or {}
        if scope.get("active_only") or scope.get("pipeline_ids") or scope.get("entry_node_id"):
            self.stdout.write(
                "Scope: "
                f"active_only={bool(scope.get('active_only'))}, "
                f"pipeline_ids={','.join(str(item) for item in scope.get('pipeline_ids') or []) or 'all'}, "
                f"entry_node_id={scope.get('entry_node_id') or 'all'}"
            )
        self.stdout.write(
            "Summary: "
            f"pipelines={summary.get('pipeline_count', 0)}, "
            f"errors={summary.get('pipeline_error_count', 0)}, "
            f"warnings={summary.get('pipeline_warning_count', 0)}, "
            f"workers_not_ready={summary.get('worker_not_ready_count', 0)}, "
            f"integration_errors={summary.get('integration_error_count', 0)}"
        )
        for issue in report.get("issues") or []:
            if issue.get("source") == "scope":
                self._write_issue(issue)
        for worker in report.get("worker_requirements") or []:
            marker = "ready" if worker.get("ready") else "not_ready"
            self.stdout.write(f"Worker {worker.get('worker')}: {marker} ({worker.get('command')})")
            for issue in worker.get("issues") or []:
                self._write_issue(issue)
        for pipeline in report.get("pipelines") or []:
            self.stdout.write(f"Pipeline #{pipeline.get('id')} {pipeline.get('name')}: {pipeline.get('status')}")
            for error in pipeline.get("errors") or []:
                self.stdout.write(self.style.ERROR(f"  error: {error}"))
            for warning in pipeline.get("warnings") or []:
                self.stdout.write(self.style.WARNING(f"  warning: {warning}"))
            for issue in pipeline.get("issues") or []:
                self._write_issue(issue)

    def _write_issue(self, issue: dict) -> None:
        style = self.style.ERROR if issue.get("severity") == "error" else self.style.WARNING
        self.stdout.write(style(f"  issue[{issue.get('code')}]: {issue.get('message')}"))
        next_action = issue.get("next_action")
        if next_action:
            self.stdout.write(f"    fix: {next_action}")
