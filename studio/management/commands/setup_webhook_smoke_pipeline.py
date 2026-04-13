from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.webhook_smoke import (
    WEBHOOK_SMOKE_CRITICAL_PAYLOAD,
    WEBHOOK_SMOKE_NORMAL_PAYLOAD,
    ensure_webhook_smoke_pipeline,
)


class Command(BaseCommand):
    help = "Create or update a minimal webhook smoke-test pipeline for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User to own the webhook smoke pipeline (default: first superuser or first user).",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        pipeline = ensure_webhook_smoke_pipeline(user)
        trigger = pipeline.triggers.filter(trigger_type="webhook", is_active=True).order_by("created_at", "id").first()
        if trigger is None:
            raise CommandError("Webhook trigger was not created for the smoke-test pipeline.")

        self.stdout.write(
            self.style.SUCCESS(
                f'Pipeline "{pipeline.name}" ready (ID={pipeline.id}) for user {user.username}.'
            )
        )
        self.stdout.write(f"Studio path: /studio/pipeline/{pipeline.id}")
        self.stdout.write(f"Webhook path: /api/studio/triggers/{trigger.webhook_token}/receive/")
        self.stdout.write("")
        self.stdout.write("Critical payload:")
        self.stdout.write(json.dumps(WEBHOOK_SMOKE_CRITICAL_PAYLOAD, ensure_ascii=False, indent=2))
        self.stdout.write("")
        self.stdout.write("Normal payload:")
        self.stdout.write(json.dumps(WEBHOOK_SMOKE_NORMAL_PAYLOAD, ensure_ascii=False, indent=2))

    def _resolve_user(self, username: str | None):
        user_model = get_user_model()
        if username:
            user = user_model.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User '{username}' not found.")
            return user

        user = user_model.objects.filter(is_superuser=True).order_by("id").first()
        if user:
            return user

        user = user_model.objects.order_by("id").first()
        if user:
            return user

        raise CommandError("No users found in the database.")
