from __future__ import annotations

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core_ui.channel_layer_health import verify_channel_layer_config


class Command(BaseCommand):
    help = "Verify the configured Channels layer can deliver direct and group messages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=float,
            default=3.0,
            help="Seconds to wait for a message round-trip.",
        )

    def handle(self, *args, **options):
        layer_config = dict(settings.CHANNEL_LAYERS.get("default") or {})
        backend = str(layer_config.get("BACKEND") or "").strip()
        if backend == "channels.layers.InMemoryChannelLayer":
            raise CommandError("InMemoryChannelLayer is not valid for production verification. Configure CHANNEL_REDIS_URL.")

        try:
            result = asyncio.run(verify_channel_layer_config(layer_config, timeout=float(options["timeout"])))
        except Exception as exc:
            raise CommandError(f"Channel layer verification failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Channel layer verified: "
                f"backend={result['backend']} group={result['group_name']}"
            )
        )
