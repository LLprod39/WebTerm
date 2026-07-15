from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.release_preflight import (
    collect_kubernetes_release_preflight,
    write_kubernetes_release_preflight,
)


class Command(BaseCommand):
    help = "Run Kubernetes Ops release preflight checks and write a bounded evidence artifact."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="artifacts/kubernetes_ops_preflight_evidence.json", help="Output JSON evidence path.")
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when preflight checks fail.")

    def handle(self, *args, **options):
        report = collect_kubernetes_release_preflight()
        output_path = write_kubernetes_release_preflight(report, Path(options["output"]).resolve())
        self.stdout.write(f"Wrote Kubernetes Ops release preflight evidence: {output_path}")
        self.stdout.write(json.dumps({"status": report["status"], "failed": report["failed"]}, ensure_ascii=False))
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(report["failed"][:8]))
