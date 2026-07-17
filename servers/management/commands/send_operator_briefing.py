"""Deliver Operator duty morning briefings.

Usage:
  python manage.py send_operator_briefing
  python manage.py send_operator_briefing --force
  python manage.py send_operator_briefing --user admin
"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send Operator duty morning briefings to eligible users"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Ignore hour/interval gates")
        parser.add_argument("--user", type=str, default="", help="Limit to one username")

    def handle(self, *args, **options):
        from core_ui.services.operator_duty import (
            deliver_briefings_for_all_users,
            deliver_morning_briefing,
        )

        force = bool(options.get("force"))
        username = str(options.get("user") or "").strip()
        if username:
            user = User.objects.filter(username=username).first()
            if user is None:
                self.stderr.write(self.style.ERROR(f"User not found: {username}"))
                return
            result = deliver_morning_briefing(user, force=force)
            self.stdout.write(self.style.SUCCESS(f"Briefing for {username}: {result}"))
            return

        summary = deliver_briefings_for_all_users(force=force)
        self.stdout.write(self.style.SUCCESS(f"Duty briefings: {summary}"))
