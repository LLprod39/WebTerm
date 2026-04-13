from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.docker_service_recovery import ensure_docker_service_recovery_pipeline


class Command(BaseCommand):
    help = "Create or update a monitoring-driven Docker service recovery pipeline for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="Pipeline owner username (default: first superuser or first user).",
        )
        parser.add_argument(
            "--server-id",
            type=int,
            default=None,
            help="Owned SSH server id to target (default: first owned SSH server).",
        )
        parser.add_argument(
            "--container-name",
            type=str,
            required=True,
            help="Docker container name to monitor and recover.",
        )
        parser.add_argument(
            "--name",
            type=str,
            default=None,
            help="Optional custom pipeline name.",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        try:
            pipeline = ensure_docker_service_recovery_pipeline(
                user,
                container_name=options["container_name"],
                server_id=options.get("server_id"),
                name=options.get("name"),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f'Pipeline "{pipeline.name}" ready (ID={pipeline.id}) for user {user.username}.'
            )
        )
        self.stdout.write(f"Studio path: /studio/pipeline/{pipeline.id}")
        for trigger in pipeline.triggers.filter(trigger_type="monitoring", is_active=True).order_by("created_at", "id"):
            self.stdout.write(
                f"Monitoring trigger ({trigger.node_id}) filters: {trigger.monitoring_filters}"
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
