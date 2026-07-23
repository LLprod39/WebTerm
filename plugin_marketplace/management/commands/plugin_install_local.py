from django.core.management.base import BaseCommand, CommandError

from plugin_marketplace.services.package_service import PluginPackageValidationError, install_local_package


class Command(BaseCommand):
    help = "Install a local WebTrerm plugin package into disabled state."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **options):
        try:
            installation = install_local_package(options["path"])
        except PluginPackageValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Installed {installation.plugin_id} as {installation.status}."))
