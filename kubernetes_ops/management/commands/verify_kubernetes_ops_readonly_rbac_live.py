from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.readonly_rbac import READONLY_SERVICE_ACCOUNT_CONTRACT
from kubernetes_ops.services.readonly_rbac_live import (
    KubectlProbeOptions,
    verify_kubernetes_readonly_rbac_live,
    write_live_rbac_evidence,
)


class Command(BaseCommand):
    help = "Verify the WebTerm Kubernetes Ops read-only RBAC manifest against a live kubectl context."

    def add_arguments(self, parser):
        parser.add_argument(
            "--manifest",
            default="artifacts/kubernetes_ops_readonly_rbac.yaml",
            help="Rendered read-only RBAC manifest path.",
        )
        parser.add_argument(
            "--output",
            default="artifacts/kubernetes_ops_readonly_rbac_live_evidence.json",
            help="Output JSON evidence path.",
        )
        parser.add_argument(
            "--apply", action="store_true", help="Apply the manifest before running kubectl auth can-i probes."
        )
        parser.add_argument("--context", default="", help="Optional kubectl context.")
        parser.add_argument("--kubectl", default="kubectl", help="kubectl executable path.")
        parser.add_argument(
            "--namespace", default=READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"], help="ServiceAccount namespace."
        )
        parser.add_argument(
            "--service-account", default=READONLY_SERVICE_ACCOUNT_CONTRACT["name"], help="ServiceAccount name."
        )
        parser.add_argument("--probe-namespace", default="default", help="Namespace used for namespaced can-i probes.")
        parser.add_argument(
            "--no-fail", action="store_true", help="Return exit code 0 even when live proof is not ready."
        )

    def handle(self, *args, **options):
        report = verify_kubernetes_readonly_rbac_live(
            KubectlProbeOptions(
                manifest_path=Path(options["manifest"]).resolve(),
                apply_manifest=bool(options["apply"]),
                context=options["context"],
                kubectl=options["kubectl"],
                service_account_namespace=options["namespace"],
                service_account_name=options["service_account"],
                probe_namespace=options["probe_namespace"],
            )
        )
        output_path = Path(options["output"]).resolve()
        write_live_rbac_evidence(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops read-only RBAC live evidence: {output_path}")
        self.stdout.write(
            json.dumps(
                {"status": report["status"], "context": report["context"], "errors": report["errors"]},
                ensure_ascii=False,
            )
        )
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(report["errors"][:8]))
