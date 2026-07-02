from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.release_interactive_transport_evidence import (
    INTERACTIVE_TRANSPORT_EVIDENCE_ARTIFACT,
    build_kubernetes_interactive_transport_evidence,
    write_kubernetes_interactive_transport_evidence,
)


class Command(BaseCommand):
    help = "Write Kubernetes Ops interactive transport prerequisite evidence without opening live streams."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=INTERACTIVE_TRANSPORT_EVIDENCE_ARTIFACT, help="Output JSON evidence path.")
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when evidence is missing.")

    def handle(self, *args, **options):
        report = build_kubernetes_interactive_transport_evidence()
        output_path = Path(options["output"]).resolve()
        write_kubernetes_interactive_transport_evidence(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops interactive transport evidence: {output_path}")
        self.stdout.write(json.dumps({"status": report["status"], "summary": report["summary"], "errors": report["errors"]}, ensure_ascii=False))
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(str(item) for item in report["errors"][:8]))
