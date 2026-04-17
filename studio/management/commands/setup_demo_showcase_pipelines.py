"""
Management command: setup_demo_showcase_pipelines

Создаёт / обновляет три безопасных демо-пайплайна для показа нодовой системы:
  1. AI Incident Triage Showcase
  2. AI Content Studio Showcase
  3. AI Data Detective Showcase

Пайплайны используют только trigger/manual, trigger/webhook, agent/llm_query,
logic/* и output/report — ничего не делают на ПК и безопасны для живой демонстрации.

Пример:
    python manage.py setup_demo_showcase_pipelines
    python manage.py setup_demo_showcase_pipelines --username admin
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from studio.demo_showcase import ensure_all_demo_showcase_pipelines


class Command(BaseCommand):
    help = "Create or update the safe demo showcase pipelines (incident triage, content studio, data detective)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User to own the demo pipelines (default: first superuser or first user).",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get("username"))
        pipelines = ensure_all_demo_showcase_pipelines(user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: создано/обновлено {len(pipelines)} демо-пайплайнов для {user.username}."
            )
        )
        for pipeline in pipelines:
            triggers = list(
                pipeline.triggers.order_by("created_at", "id").values_list("trigger_type", flat=True)
            )
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(f"• {pipeline.icon} {pipeline.name} (ID={pipeline.id})"))
            self.stdout.write(f"  Studio path: /studio/pipeline/{pipeline.id}")
            self.stdout.write(f"  Triggers:    {', '.join(triggers) or '—'}")
            for trigger in pipeline.triggers.filter(trigger_type="webhook", is_active=True).order_by("created_at", "id"):
                self.stdout.write(
                    f"  Webhook ({trigger.node_id}): /api/studio/triggers/{trigger.webhook_token}/receive/"
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

        raise CommandError("В базе нет пользователей. Сначала создайте суперпользователя.")
