from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.models import Pipeline
from studio.readiness import build_studio_readiness_report
from studio.readiness_repair import deactivate_pipeline_trigger_nodes, quarantine_candidates


class Command(BaseCommand):
    help = "Dry-run or apply a safe quarantine for active Studio triggers on not-ready pipelines."

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, default=None, help="Scope the repair to one user's pipelines.")
        parser.add_argument(
            "--pipeline-id",
            action="append",
            type=int,
            default=None,
            help="Limit the repair to one pipeline id. Can be passed more than once.",
        )
        parser.add_argument(
            "--include-warnings",
            action="store_true",
            help="Also quarantine warning pipelines. By default only error/not_ready pipelines are selected.",
        )
        parser.add_argument("--apply", action="store_true", help="Apply the quarantine. Without this, only report candidates.")
        parser.add_argument("--json", action="store_true", help="Print machine-readable output.")

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        report = build_studio_readiness_report(
            user,
            pipeline_ids=options.get("pipeline_id"),
            active_only=True,
        )
        candidates = quarantine_candidates(report, include_warnings=bool(options.get("include_warnings")))
        applied = []

        if options.get("apply"):
            for candidate in candidates:
                pipeline = Pipeline.objects.filter(pk=candidate["pipeline_id"]).first()
                if pipeline is None:
                    continue
                disabled = deactivate_pipeline_trigger_nodes(pipeline, candidate["trigger_node_ids"])
                applied.append({**candidate, "disabled_trigger_node_ids": disabled})

        payload = {
            "applied": bool(options.get("apply")),
            "candidate_count": len(candidates),
            "disabled_count": sum(len(item.get("disabled_trigger_node_ids") or []) for item in applied),
            "candidates": candidates,
            "applied_items": applied,
        }
        if options.get("json"):
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            return
        self._write_human_report(payload)

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

    def _write_human_report(self, payload: dict) -> None:
        mode = "APPLY" if payload["applied"] else "DRY-RUN"
        self.stdout.write(f"Studio trigger quarantine {mode}: candidates={payload['candidate_count']}")
        source_items = payload["applied_items"] if payload["applied"] else payload["candidates"]
        for item in source_items:
            trigger_ids = item.get("disabled_trigger_node_ids") or item.get("trigger_node_ids") or []
            self.stdout.write(
                f"Pipeline #{item.get('pipeline_id')} {item.get('pipeline_name')}: "
                f"status={item.get('status')} triggers={','.join(trigger_ids)} "
                f"issues={','.join(item.get('issue_codes') or []) or 'none'}"
            )
        if not payload["applied"]:
            self.stdout.write("No changes applied. Re-run with --apply to disable these trigger nodes.")
