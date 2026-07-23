from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from kubernetes_ops.services.action_verification import run_pending_native_action_verifications


class Command(BaseCommand):
    help = "Evaluate pending WebTerm-native Kubernetes action verification plans from read-only inventory."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=50, help="Maximum executed-native action requests to evaluate."
        )
        parser.add_argument("--as-json", action="store_true", help="Write the summary as JSON.")

    def handle(self, *args, **options):
        try:
            summary = run_pending_native_action_verifications(limit=options["limit"])
        except (OperationalError, ProgrammingError) as exc:
            raise CommandError(
                "Kubernetes Ops tables are not ready. Run `python manage.py migrate kubernetes_ops`."
            ) from exc

        if options["as_json"]:
            self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
            return
        self.stdout.write(
            self.style.SUCCESS(
                "Native action verification processed={processed} verified={verified} "
                "needs_review={needs_review} skipped={skipped}".format(**summary)
            )
        )
