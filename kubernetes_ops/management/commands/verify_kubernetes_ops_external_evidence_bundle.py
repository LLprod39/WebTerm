from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.release_external_evidence_bundle import (
    EXTERNAL_EVIDENCE_BUNDLE_ARTIFACT,
    build_kubernetes_external_evidence_bundle,
    write_kubernetes_external_evidence_bundle,
)


class Command(BaseCommand):
    help = "Write Kubernetes Ops external production evidence bundle gate."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=EXTERNAL_EVIDENCE_BUNDLE_ARTIFACT, help="Output JSON evidence path.")
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when evidence is missing.")

    def handle(self, *args, **options):
        report = build_kubernetes_external_evidence_bundle()
        output_path = Path(options["output"]).resolve()
        write_kubernetes_external_evidence_bundle(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops external evidence bundle: {output_path}")
        self.stdout.write(
            json.dumps(
                {"status": report["status"], "summary": report["summary"], "errors": report["errors"]},
                ensure_ascii=False,
            )
        )
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(str(item) for item in report["errors"][:8]))
