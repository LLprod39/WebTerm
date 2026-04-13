"""
Management command: load_pipeline_templates

Loads or updates the built-in pipeline templates into the database.

Usage:
    python manage.py load_pipeline_templates
    python manage.py load_pipeline_templates --force  # overwrite existing
"""

from django.core.management.base import BaseCommand

from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, PipelineTemplate
from studio.templates_data import PIPELINE_TEMPLATES


class Command(BaseCommand):
    help = "Load built-in pipeline templates into the database"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Overwrite existing templates")

    def handle(self, *args, **options):
        force = options["force"]
        created = updated = skipped = 0

        for tpl in PIPELINE_TEMPLATES:
            slug = tpl["slug"]
            existing = PipelineTemplate.objects.filter(slug=slug).first()

            if existing and not force:
                skipped += 1
                continue

            defaults = {k: v for k, v in tpl.items() if k != "slug"}
            defaults.setdefault("graph_version", CURRENT_PIPELINE_GRAPH_VERSION)
            _, was_created = PipelineTemplate.objects.update_or_create(slug=slug, defaults=defaults)

            if was_created:
                created += 1
                self.stdout.write(f"  Created: {tpl['name']}")
            else:
                updated += 1
                self.stdout.write(f"  Updated: {tpl['name']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created} created, {updated} updated, {skipped} skipped"
            )
        )
