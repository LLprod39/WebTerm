from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plugin_marketplace.models import MarketplaceCatalogItem
from plugin_marketplace.services.compatibility_matrix_service import compatibility_checks_for_item


class Command(BaseCommand):
    help = "Run no-code compatibility checks for one private catalog item and print JSON."

    def add_arguments(self, parser):
        parser.add_argument("--catalog-item-id", type=int, required=True)

    def handle(self, *args, **options):
        item_id = int(options["catalog_item_id"])
        try:
            item = MarketplaceCatalogItem.objects.select_related("source").get(id=item_id)
        except MarketplaceCatalogItem.DoesNotExist as exc:
            raise CommandError(f"Private catalog item {item_id} was not found.") from exc
        self.stdout.write(json.dumps(compatibility_checks_for_item(item), sort_keys=True))
