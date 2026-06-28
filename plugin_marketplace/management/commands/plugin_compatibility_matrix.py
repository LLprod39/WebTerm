from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plugin_marketplace.services.compatibility_matrix_service import (
    build_compatibility_matrix,
    compatibility_summary,
    incompatible_compatibility_messages,
    run_compatibility_matrix_update,
)


class Command(BaseCommand):
    help = "Build or update the private plugin catalog compatibility matrix for release gates."

    def add_arguments(self, parser):
        parser.add_argument("--update", action="store_true", help="Persist compatibility jobs and update catalog item matrix state.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Print the compatibility matrix payload as JSON.")
        parser.add_argument(
            "--fail-on-incompatible",
            action="store_true",
            help="Exit with an error when any private catalog item is incompatible.",
        )

    def handle(self, *args, **options):
        items = run_compatibility_matrix_update() if options.get("update") else build_compatibility_matrix()
        payload = {"success": True, "items": items, "summary": compatibility_summary(items)}

        if options.get("as_json"):
            self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=str))
        else:
            summary = payload["summary"]
            mode = "updated" if options.get("update") else "checked"
            self.stdout.write(
                f"compatibility matrix {mode}: "
                f"{summary['compatible']}/{summary['total']} compatible, "
                f"{summary['incompatible']} incompatible"
            )
            for item in items:
                status = "compatible" if item.get("compatible") else "incompatible"
                self.stdout.write(f"{item.get('plugin_id')}@{item.get('version')}: {status}")

        if options.get("fail_on_incompatible"):
            messages = incompatible_compatibility_messages(items)
            if messages:
                raise CommandError("; ".join(messages))
