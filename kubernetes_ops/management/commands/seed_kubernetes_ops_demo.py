from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from kubernetes_ops.services.demo_seed import seed_kubernetes_ops_demo_inventory


class Command(BaseCommand):
    help = "Seed a safe local Kubernetes Ops demo inventory without calling external providers."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin", help="Existing user to grant Kubernetes demo access to.")
        parser.add_argument(
            "--no-permissions", action="store_true", help="Only seed inventory; do not grant user feature access."
        )
        parser.add_argument(
            "--admin-write", action="store_true", help="Also grant Kubernetes Admin Write for local demo testing."
        )
        parser.add_argument("--json", action="store_true", help="Print a JSON summary.")

    def handle(self, *args, **options):
        result = seed_kubernetes_ops_demo_inventory(
            username=str(options["username"] or "admin"),
            grant_permissions=not bool(options["no_permissions"]),
            grant_admin_write=bool(options["admin_write"]),
        )
        if options["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded Kubernetes Ops demo inventory: cluster={result['cluster']} counts={result['demo_counts']}"
            )
        )
        user = result.get("user") if isinstance(result.get("user"), dict) else {}
        if user.get("found"):
            granted = ", ".join(item.get("feature", "") for item in user.get("granted") or [])
            self.stdout.write(f"Granted demo access to {user.get('username')}: {granted}")
        elif not options["no_permissions"]:
            self.stdout.write(self.style.WARNING(f"User {options['username']!r} was not found; inventory was seeded."))
