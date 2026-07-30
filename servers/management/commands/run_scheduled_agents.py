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

from servers.agents.scheduled_agents import dispatch_scheduled_agents
from servers.models import BackgroundWorkerState
from servers.worker_state import (
    claim_background_worker,
    cleanup_stale_background_workers,
    heartbeat_background_worker,
    stop_background_worker,
)


class Command(BaseCommand):
    help = "Poll and dispatch scheduled server agents."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
        parser.add_argument("--daemon", action="store_true", help="Run continuously until interrupted")
        parser.add_argument("--once", action="store_true", help="Run one dispatch cycle and exit")
        parser.add_argument("--limit", type=int, default=100, help="Maximum number of scheduled agents to inspect")
        parser.add_argument(
            "--agent-id", type=int, action="append", dest="agent_ids", help="Only dispatch specific agent id"
        )
        parser.add_argument(
            "--user-id", type=int, action="append", dest="user_ids", help="Only dispatch agents for specific user id"
        )
        parser.add_argument("--lease-seconds", type=int, default=180, help="Heartbeat lease duration for this worker")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key")

    def handle(self, *args, **options):
        interval = max(15, int(options["interval"]))
        daemon = bool(options["daemon"])
        once = bool(options["once"])
        limit = max(1, min(int(options["limit"]), 500))
        agent_ids = options.get("agent_ids") or []
        user_ids = options.get("user_ids") or []
        lease_seconds = max(30, int(options["lease_seconds"]))
        worker_key = str(options["worker_key"] or "default").strip() or "default"
        worker_kind = BackgroundWorkerState.KIND_SCHEDULED_AGENTS

        cleanup_stale_background_workers(worker_kind)
        command = f"python manage.py run_scheduled_agents --daemon --worker-key {worker_key}"
        state = claim_background_worker(
            worker_kind,
            worker_key=worker_key,
            command=command,
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(
                self.style.WARNING(f"Scheduled agents worker {worker_key!r} is already leased by another process")
            )
            return

        self.stdout.write(self.style.SUCCESS(f"Starting scheduled agent dispatcher ({worker_key})..."))
        last_summary = {"scanned": 0, "due": 0, "launched_agents": 0, "runs_created": 0, "skipped": 0}
        error = ""
        try:
            if once or not daemon:
                last_summary = self._tick(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    limit=limit,
                    agent_ids=agent_ids,
                    user_ids=user_ids,
                )
                self.stdout.write(self.style.SUCCESS(self._format_summary(last_summary)))
                return

            while True:
                last_summary = self._tick(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    limit=limit,
                    agent_ids=agent_ids,
                    user_ids=user_ids,
                )
                self.stdout.write(self.style.SUCCESS(self._format_summary(last_summary)))
                self.stdout.write(f"Next check in {interval}s...")
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nScheduled agent dispatcher stopped by user"))
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            stop_background_worker(worker_kind, worker_key=worker_key, summary=last_summary, error=error)

    def _tick(
        self, *, worker_key: str, lease_seconds: int, limit: int, agent_ids: list[int], user_ids: list[int]
    ) -> dict:
        worker_kind = BackgroundWorkerState.KIND_SCHEDULED_AGENTS
        heartbeat_background_worker(
            worker_kind,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            cycle_started=True,
        )
        try:
            from app.core.ops_controls import assert_schedulers_not_paused

            paused = assert_schedulers_not_paused()
        except Exception:
            paused = None
        if paused:
            self.stdout.write(self.style.WARNING(paused))
            return {"scanned": 0, "due": 0, "launched_agents": 0, "runs_created": 0, "skipped": 1, "paused": True}
        summary = dispatch_scheduled_agents(limit=limit, agent_ids=agent_ids, user_ids=user_ids)
        heartbeat_background_worker(
            worker_kind,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            summary=summary,
            cycle_finished=True,
        )
        return summary

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
