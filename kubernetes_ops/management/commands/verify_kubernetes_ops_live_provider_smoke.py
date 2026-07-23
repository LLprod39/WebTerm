from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from kubernetes_ops.services.live_provider_smoke import (
    LIVE_PROVIDER_SMOKE_ARTIFACT,
    build_kubernetes_live_provider_smoke,
    write_live_provider_smoke,
)


class Command(BaseCommand):
    help = "Verify live Rancher/Fleet/Devtron provider probes and dry-run sync, then write bounded evidence."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=LIVE_PROVIDER_SMOKE_ARTIFACT, help="Output JSON evidence path.")
        parser.add_argument("--skip-probe", action="store_true", help="Skip live provider probe calls.")
        parser.add_argument("--skip-sync-dry-run", action="store_true", help="Skip provider sync dry-run calls.")
        parser.add_argument(
            "--allow-missing-rancher", action="store_true", help="Do not fail when no enabled Rancher provider exists."
        )
        parser.add_argument(
            "--allow-missing-devtron", action="store_true", help="Do not fail when no enabled Devtron provider exists."
        )
        parser.add_argument(
            "--allow-missing-fleet", action="store_true", help="Do not fail when Rancher sync returns no Fleet bundles."
        )
        parser.add_argument(
            "--skip-backend-paths", action="store_true", help="Skip Admin backend path smoke for synced pod YAML/logs."
        )
        parser.add_argument(
            "--allow-missing-backend-paths",
            action="store_true",
            help="Do not fail when Admin backend path smoke is missing or failed.",
        )
        parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when smoke checks fail.")

    def handle(self, *args, **options):
        report = build_kubernetes_live_provider_smoke(
            run_provider_probe=not bool(options["skip_probe"]),
            run_sync_dry_run=not bool(options["skip_sync_dry_run"]),
            require_rancher=not bool(options["allow_missing_rancher"]),
            require_devtron=not bool(options["allow_missing_devtron"]),
            require_fleet=not bool(options["allow_missing_fleet"]),
            run_backend_paths=not bool(options["skip_backend_paths"]),
            require_backend_paths=not bool(options["allow_missing_backend_paths"]),
        )
        output_path = Path(options["output"]).resolve()
        write_live_provider_smoke(report, output_path)
        self.stdout.write(f"Wrote Kubernetes Ops live provider smoke evidence: {output_path}")
        self.stdout.write(
            json.dumps(
                {"status": report["status"], "summary": report["summary"], "errors": report["errors"]},
                ensure_ascii=False,
            )
        )
        if report["status"] != "ready" and not options["no_fail"]:
            raise CommandError("; ".join(report["errors"][:8]))
