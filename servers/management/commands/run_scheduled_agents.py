"""
Management command: run_scheduled_agents

Dispatches enabled server agents whose ``schedule_minutes`` window is due.

Usage:
    python manage.py run_scheduled_agents --once
    python manage.py run_scheduled_agents --daemon --interval 60
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from servers.scheduled_agents import dispatch_scheduled_agents


class Command(BaseCommand):
    help = "Poll and dispatch scheduled server agents."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
        parser.add_argument("--daemon", action="store_true", help="Run continuously until interrupted")
        parser.add_argument("--once", action="store_true", help="Run one dispatch cycle and exit")
        parser.add_argument("--limit", type=int, default=100, help="Maximum number of scheduled agents to inspect")
        parser.add_argument("--agent-id", type=int, action="append", dest="agent_ids", help="Only dispatch specific agent id")
        parser.add_argument("--user-id", type=int, action="append", dest="user_ids", help="Only dispatch agents for specific user id")

    def handle(self, *args, **options):
        interval = max(15, int(options["interval"]))
        daemon = bool(options["daemon"])
        once = bool(options["once"])
        limit = max(1, min(int(options["limit"]), 500))
        agent_ids = options.get("agent_ids") or []
        user_ids = options.get("user_ids") or []

        self.stdout.write("Starting scheduled agent dispatcher...")
        if once or not daemon:
            summary = self._tick(limit=limit, agent_ids=agent_ids, user_ids=user_ids)
            self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
            return

        while True:
            summary = self._tick(limit=limit, agent_ids=agent_ids, user_ids=user_ids)
            self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
            self.stdout.write(f"Next check in {interval}s...")
            time.sleep(interval)

    def _tick(self, *, limit: int, agent_ids: list[int], user_ids: list[int]) -> dict:
        return dispatch_scheduled_agents(limit=limit, agent_ids=agent_ids, user_ids=user_ids)

    @staticmethod
    def _format_summary(summary: dict) -> str:
        skip_reasons = summary.get("skip_reasons") or {}
        return (
            f"scanned={summary.get('scanned', 0)} "
            f"due={summary.get('due', 0)} "
            f"launched_agents={summary.get('launched_agents', 0)} "
            f"runs_created={summary.get('runs_created', 0)} "
            f"background_runs={summary.get('background_runs', 0)} "
            f"mini_runs={summary.get('mini_runs', 0)} "
            f"skipped={summary.get('skipped', 0)} "
            f"skip_active={skip_reasons.get('active_run', 0)} "
            f"skip_limit={skip_reasons.get('limit', 0)} "
            f"skip_not_due={skip_reasons.get('not_due', 0)}"
        )
