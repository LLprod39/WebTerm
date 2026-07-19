"""Global kill switch for pipelines/agents.

Usage:
  python manage.py ops_kill_switch --pause --reason "incident"
  python manage.py ops_kill_switch --resume
  python manage.py ops_kill_switch --status
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from studio.ops_controls import get_ops_control_status, set_ops_paused


class Command(BaseCommand):
    help = "Pause or resume all scheduled pipelines/agents and block new agent starts"

    def add_arguments(self, parser):
        parser.add_argument("--pause", action="store_true", help="Activate global pause")
        parser.add_argument("--resume", action="store_true", help="Clear global pause")
        parser.add_argument("--status", action="store_true", help="Show current state")
        parser.add_argument("--reason", type=str, default="", help="Pause reason")
        parser.add_argument("--actor", type=str, default="", help="Operator identity")

    def handle(self, *args, **options):
        if options.get("pause") and options.get("resume"):
            self.stderr.write("Choose only one of --pause or --resume")
            return
        if options.get("pause"):
            payload = set_ops_paused(True, reason=options.get("reason") or "Paused by operator", actor=options.get("actor") or "")
            self.stdout.write(self.style.WARNING(f"Kill switch ON: {payload}"))
            return
        if options.get("resume"):
            payload = set_ops_paused(False, reason="", actor=options.get("actor") or "")
            self.stdout.write(self.style.SUCCESS(f"Kill switch OFF: {payload}"))
            return
        status = get_ops_control_status()
        self.stdout.write(str(status))
