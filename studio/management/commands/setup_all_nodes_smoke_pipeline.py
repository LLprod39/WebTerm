from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.all_nodes_smoke import ensure_all_nodes_smoke_pipeline


class Command(BaseCommand):
    help = "Create or update the large all-nodes smoke-test pipeline for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User to own the all-nodes smoke pipeline (default: first superuser or first user).",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        pipeline = ensure_all_nodes_smoke_pipeline(user)
        trigger_types = list(
            pipeline.triggers.order_by("created_at", "id").values_list("trigger_type", flat=True)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Pipeline "{pipeline.name}" ready (ID={pipeline.id}) for user {user.username}.'
            )
        )
        self.stdout.write(f"Studio path: /studio/pipeline/{pipeline.id}")
        self.stdout.write(f"Triggers: {', '.join(trigger_types)}")
        for trigger in pipeline.triggers.filter(trigger_type="webhook", is_active=True).order_by("created_at", "id"):
            self.stdout.write(
                f"Webhook path ({trigger.node_id}): /api/studio/triggers/{trigger.webhook_token}/receive/"
            )

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
