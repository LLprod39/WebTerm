from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.local_platform_evidence import (
    LocalPlatformProbeOptions,
    verify_kubernetes_local_platform,
    write_local_platform_evidence,
)


class Command(BaseCommand):
    help = "Verify the local kind Rancher/Fleet/Devtron platform and write a bounded evidence artifact."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default="artifacts/kubernetes_ops_local_platform_evidence.json",
            help="Output JSON evidence path.",
        )
        parser.add_argument("--context", default="kind-webterm-k8s", help="Expected kubectl context.")
        parser.add_argument("--kubectl", default="kubectl", help="kubectl executable path.")
        parser.add_argument(
            "--no-context-requirement",
            action="store_true",
            help="Do not fail when current context differs from --context.",
        )
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when platform checks fail.")

    def handle(self, *args, **options):
        report = verify_kubernetes_local_platform(
            LocalPlatformProbeOptions(
                context=str(options["context"] or ""),
                kubectl=str(options["kubectl"] or "kubectl"),
                require_context=not bool(options["no_context_requirement"]),
            )
        )
        output_path = Path(options["output"]).resolve()
        write_local_platform_evidence(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops local platform evidence: {output_path}")
        self.stdout.write(
            json.dumps(
                {"status": report["status"], "summary": report["summary"], "errors": report["errors"]},
                ensure_ascii=False,
            )
        )
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(report["errors"][:8]))
