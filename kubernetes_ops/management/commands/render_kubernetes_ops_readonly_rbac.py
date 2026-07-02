from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.readonly_rbac import (
    READONLY_SERVICE_ACCOUNT_CONTRACT,
    build_kubernetes_readonly_rbac_bundle,
    render_kubernetes_readonly_rbac_json,
    render_kubernetes_readonly_rbac_yaml,
    validate_kubernetes_readonly_rbac_bundle,
)


class Command(BaseCommand):
    help = "Render the read-only Kubernetes RBAC manifest used by WebTerm Kubernetes Ops."

    def add_arguments(self, parser):
        parser.add_argument("--namespace", default=READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"], help="Namespace for the ServiceAccount.")
        parser.add_argument(
            "--service-account",
            default=READONLY_SERVICE_ACCOUNT_CONTRACT["name"],
            help="Read-only ServiceAccount name.",
        )
        parser.add_argument("--format", choices=["yaml", "json"], default="yaml", help="Manifest output format.")
        parser.add_argument("--output", help="Optional output path.")
        parser.add_argument("--validate-only", action="store_true", help="Validate the manifest and print no YAML/JSON payload.")

    def handle(self, *args, **options):
        bundle = build_kubernetes_readonly_rbac_bundle(
            namespace=options["namespace"],
            service_account_name=options["service_account"],
        )
        validation = validate_kubernetes_readonly_rbac_bundle(bundle)
        if validation["status"] != "ready":
            raise CommandError("; ".join(validation["errors"]))

        if options["validate_only"]:
            self.stdout.write(self.style.SUCCESS("Kubernetes Ops read-only RBAC manifest is valid."))
            return

        payload = render_kubernetes_readonly_rbac_json(bundle) if options["format"] == "json" else render_kubernetes_readonly_rbac_yaml(bundle)
        output_path = options.get("output")
        if output_path:
            path = Path(output_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            self.stdout.write(f"Wrote Kubernetes Ops read-only RBAC manifest: {path}")
            return
        self.stdout.write(payload)
