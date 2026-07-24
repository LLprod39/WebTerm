from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from plugin_marketplace.services.developer_package_service import pack_plugin_source
from plugin_marketplace.services.package_service import PluginPackageValidationError


class Command(BaseCommand):
    help = "Pack a WebTerm plugin source directory into a deterministic .wtp archive."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--output-dir", dest="output_dir", default=None)
        parser.add_argument("--output", dest="output_path", default=None)
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options):
        try:
            result = pack_plugin_source(
                options["path"],
                output_dir=options.get("output_dir"),
                output_path=options.get("output_path"),
                overwrite=bool(options.get("overwrite")),
            )
        except PluginPackageValidationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Packed {result.plugin_id}@{result.version} -> {result.path} ({result.sha256}).")
        )
