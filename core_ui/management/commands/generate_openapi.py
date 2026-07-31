from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core_ui.schemas.openapi import build_openapi_document


class Command(BaseCommand):
    help = "Generate or verify the published OpenAPI document."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Fail when the committed schema is stale")
        parser.add_argument("--output", default="docs/openapi.json", help="Output path relative to the repository")

    def handle(self, *args, **options):
        output = Path(options["output"])
        if not output.is_absolute():
            output = Path(settings.BASE_DIR) / output
        rendered = json.dumps(build_openapi_document(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if options["check"]:
            if not output.exists() or output.read_text(encoding="utf-8") != rendered:
                raise CommandError(f"OpenAPI document is stale; run manage.py generate_openapi ({output})")
            self.stdout.write(self.style.SUCCESS(f"OpenAPI document is current: {output}"))
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        self.stdout.write(self.style.SUCCESS(f"Wrote {output}"))
