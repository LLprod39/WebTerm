from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.sync import sync_kubernetes_providers


class Command(BaseCommand):
    help = "Sync read-only Kubernetes Ops inventory from enabled Rancher/Fleet/Devtron providers."

    def add_arguments(self, parser):
        parser.add_argument("--provider-id", type=int, default=None, help="Sync one provider by database id.")
        parser.add_argument(
            "--kind",
            choices=[K8sProvider.KIND_RANCHER, K8sProvider.KIND_DEVTRON],
            default="",
            help="Sync enabled providers of one kind.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize data without writing DB rows.")

    def handle(self, *args, **options):
        try:
            results = sync_kubernetes_providers(
                provider_id=options.get("provider_id"),
                kind=options.get("kind") or "",
                dry_run=bool(options.get("dry_run")),
            )
        except (OperationalError, ProgrammingError) as exc:
            raise CommandError(
                "Kubernetes Ops tables are not ready. Run `python manage.py migrate kubernetes_ops`."
            ) from exc
        if not results:
            self.stdout.write(self.style.WARNING("No enabled Kubernetes providers matched the sync filters."))
            return

        failed = [item for item in results if not item.success]
        for item in results:
            status = "OK" if item.success else "FAILED"
            self.stdout.write(
                f"{status} provider={item.provider_name} kind={item.provider_kind} "
                f"clusters={item.clusters} namespaces={item.namespaces} workloads={item.workloads} "
                f"pods={item.pods} services={item.services} ingresses={item.ingresses} events={item.events} "
                f"apps={item.apps} fleet_bundles={item.fleet_bundles}"
            )
            if item.error:
                self.stdout.write(f"  error={item.error}")

        if failed:
            raise CommandError(f"{len(failed)} Kubernetes provider sync(s) failed.")
        self.stdout.write(self.style.SUCCESS(f"Synced {len(results)} Kubernetes provider(s)."))
