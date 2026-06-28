from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from plugin_marketplace.services.developer_package_service import validate_plugin_source_dir
from plugin_marketplace.services.package_service import PluginPackageValidationError, validate_wtp_package


class Command(BaseCommand):
    help = "Validate a WebTrerm plugin source directory or .wtp package without executing package contents."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **options):
        target = options["path"]
        try:
            if Path(target).is_dir():
                result = validate_plugin_source_dir(target)
            else:
                result = validate_wtp_package(target)
        except PluginPackageValidationError as exc:
            raise CommandError(str(exc)) from exc
        if not result.ok:
            raise CommandError("; ".join(result.errors))
        digest = getattr(result, "sha256", "source")
        self.stdout.write(self.style.SUCCESS(f"{result.plugin_id}@{result.version} is valid ({digest})."))
