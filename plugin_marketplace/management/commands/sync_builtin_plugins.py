from django.core.management.base import BaseCommand

from plugin_marketplace.services.install_service import ensure_builtin_packages


class Command(BaseCommand):
    help = "Sync built-in plugin manifests into the local extension store."

    def handle(self, *args, **options):
        installations = ensure_builtin_packages()
        self.stdout.write(self.style.SUCCESS(f"Synced {len(installations)} built-in plugin installation(s)."))
