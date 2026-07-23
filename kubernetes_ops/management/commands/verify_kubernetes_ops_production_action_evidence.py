from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.release_production_action_evidence import (
    PRODUCTION_ACTION_EVIDENCE_ARTIFACT,
    build_kubernetes_production_action_evidence,
    write_kubernetes_production_action_evidence,
)


class Command(BaseCommand):
    help = "Write Kubernetes Ops production rollback/native verification evidence without mutating the cluster."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=PRODUCTION_ACTION_EVIDENCE_ARTIFACT, help="Output JSON evidence path.")
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when evidence is missing.")

    def handle(self, *args, **options):
        report = build_kubernetes_production_action_evidence()
        output_path = Path(options["output"]).resolve()
        write_kubernetes_production_action_evidence(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops production action evidence: {output_path}")
        self.stdout.write(
            json.dumps(
                {"status": report["status"], "summary": report["summary"], "errors": report["errors"]},
                ensure_ascii=False,
            )
        )
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(str(item) for item in report["errors"][:8]))
