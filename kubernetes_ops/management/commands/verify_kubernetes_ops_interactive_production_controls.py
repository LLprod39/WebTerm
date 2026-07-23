from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.release_interactive_production_controls import (
    INTERACTIVE_PRODUCTION_CONTROLS_ARTIFACT,
    build_kubernetes_interactive_production_controls,
    write_kubernetes_interactive_production_controls,
)


class Command(BaseCommand):
    help = "Write Kubernetes Ops interactive production controls evidence without opening live streams."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", default=INTERACTIVE_PRODUCTION_CONTROLS_ARTIFACT, help="Output JSON evidence path."
        )
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when evidence is missing.")

    def handle(self, *args, **options):
        report = build_kubernetes_interactive_production_controls()
        output_path = Path(options["output"]).resolve()
        write_kubernetes_interactive_production_controls(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops interactive production controls evidence: {output_path}")
        self.stdout.write(
            json.dumps(
                {"status": report["status"], "summary": report["summary"], "errors": report["errors"]},
                ensure_ascii=False,
            )
        )
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(str(item) for item in report["errors"][:8]))
