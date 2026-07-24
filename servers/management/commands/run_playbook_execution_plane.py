from __future__ import annotations

import signal
import sys
import threading

from django.core.management.base import BaseCommand, CommandError
from loguru import logger

from app.core.redacted_logging import redacted_log_text
from servers.models import PlaybookRunDispatch
from servers.playbook_dispatch import (
    DEFAULT_PLAYBOOK_LEASE_SECONDS,
    PLAYBOOK_EXECUTION_WORKER_KIND,
    claim_next_playbook_dispatch,
    execute_playbook_dispatch,
    recover_expired_playbook_dispatches,
)
from servers.services.ansible_docker_runtime import scavenge_ansible_workdirs
from servers.services.playbook_run_state import deliver_pending_playbook_run_notifications
from servers.worker_state import (
    claim_background_worker,
    cleanup_stale_background_workers,
    heartbeat_background_worker,
    stop_background_worker,
)


class Command(BaseCommand):
    help = "Run the durable execution-plane worker for queued Ansible playbook runs."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5, help="Queue poll interval in seconds")
        parser.add_argument(
            "--lease-seconds",
            type=int,
            default=DEFAULT_PLAYBOOK_LEASE_SECONDS,
            help="Worker and dispatch heartbeat lease duration",
        )
        parser.add_argument("--limit", type=int, default=100, help="Maximum rows processed with --once")
        parser.add_argument("--worker-key", type=str, default="default", help="Stable worker instance key")
        parser.add_argument(
            "--global-concurrency",
            type=int,
            default=None,
            help="Override the database-enforced global playbook execution limit",
        )
        parser.add_argument(
            "--per-user-concurrency",
            type=int,
            default=None,
            help="Override the database-enforced per-user playbook execution limit",
        )
        parser.add_argument("--once", action="store_true", help="Drain currently claimable rows once and exit")

    def handle(self, *args, **options):
        interval = max(1, min(int(options["interval"]), 60))
        lease_seconds = max(30, int(options["lease_seconds"]))
        limit = max(1, min(int(options["limit"]), 500))
        worker_key = str(options["worker_key"] or "default").strip()[:80] or "default"
        global_concurrency = options.get("global_concurrency")
        per_user_concurrency = options.get("per_user_concurrency")
        once = bool(options["once"])
        stop_requested = threading.Event()
        previous_handlers: dict[signal.Signals, object] = {}
        if not once and sys.platform != "win32":
            for sig_name in ("SIGINT", "SIGTERM"):
                sig = getattr(signal, sig_name, None)
                if sig is not None:
                    previous_handlers[sig] = signal.getsignal(sig)
                    signal.signal(sig, lambda _signum, _frame: stop_requested.set())

        cleanup_stale_background_workers(PLAYBOOK_EXECUTION_WORKER_KIND)
        artifact_cleanup = scavenge_ansible_workdirs()
        if any(artifact_cleanup.values()):
            logger.info("Ansible runtime artifact cleanup: {}", artifact_cleanup)
        state = claim_background_worker(
            PLAYBOOK_EXECUTION_WORKER_KIND,
            worker_key=worker_key,
            command=f"python manage.py run_playbook_execution_plane --worker-key {worker_key}",
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Playbook worker {worker_key!r} is already leased"))
            return

        self.stdout.write(self.style.SUCCESS(f"Starting playbook execution worker ({worker_key})"))
        summary = self._empty_summary()
        fatal_error = ""
        try:
            if once:
                summary = self._run_once(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    limit=limit,
                    global_concurrency=global_concurrency,
                    per_user_concurrency=per_user_concurrency,
                    shutdown_event=stop_requested,
                )
                self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
                if summary["failed"]:
                    raise CommandError(f"Playbook execution dispatches failed: {summary['failed']}")
                return

            while not stop_requested.is_set():
                cycle = self._run_once(
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    limit=1,
                    global_concurrency=global_concurrency,
                    per_user_concurrency=per_user_concurrency,
                    shutdown_event=stop_requested,
                )
                for key, value in cycle.items():
                    summary[key] = int(summary.get(key) or 0) + int(value or 0)
                if cycle["empty_polls"]:
                    stop_requested.wait(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nPlaybook execution worker stopped by user"))
        except CommandError:
            raise
        except Exception as exc:
            fatal_error = redacted_log_text(f"{exc.__class__.__name__}: {exc}", limit=4000)
            logger.error("Playbook execution worker crashed: {}", fatal_error)
            raise
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
            stop_background_worker(
                PLAYBOOK_EXECUTION_WORKER_KIND,
                worker_key=worker_key,
                summary=summary,
                error=fatal_error,
            )

    def _run_once(
        self,
        *,
        worker_key: str,
        lease_seconds: int,
        limit: int,
        global_concurrency: int | None,
        per_user_concurrency: int | None,
        shutdown_event: threading.Event | None = None,
    ) -> dict[str, int]:
        summary = self._empty_summary()
        summary["notifications"] += deliver_pending_playbook_run_notifications(limit=limit)
        for _index in range(limit):
            if shutdown_event is not None and shutdown_event.is_set():
                break
            recovered = recover_expired_playbook_dispatches()
            summary["requeued"] += recovered["requeued"]
            summary["interrupted"] += recovered["interrupted"]
            summary["canceled"] += recovered["canceled"]
            heartbeat_background_worker(
                PLAYBOOK_EXECUTION_WORKER_KIND,
                worker_key=worker_key,
                lease_seconds=lease_seconds,
                summary=summary,
                cycle_started=True,
            )
            dispatch = claim_next_playbook_dispatch(
                worker_name=worker_key,
                lease_seconds=lease_seconds,
                global_concurrency=global_concurrency,
                per_user_concurrency=per_user_concurrency,
            )
            if dispatch is None:
                summary["empty_polls"] += 1
                heartbeat_background_worker(
                    PLAYBOOK_EXECUTION_WORKER_KIND,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary,
                    cycle_finished=True,
                )
                break

            try:
                execute_playbook_dispatch(
                    dispatch.id,
                    worker_name=worker_key,
                    lease_seconds=lease_seconds,
                    shutdown_event=shutdown_event,
                )
                dispatch.refresh_from_db()
                if dispatch.status in {
                    PlaybookRunDispatch.STATUS_FAILED,
                    PlaybookRunDispatch.STATUS_INTERRUPTED,
                }:
                    summary["failed"] += 1
                elif dispatch.status == PlaybookRunDispatch.STATUS_CANCELED:
                    summary["canceled"] += 1
                else:
                    summary["completed"] += 1
            except Exception as exc:
                logger.error(
                    "Playbook dispatch {} failed: {}",
                    dispatch.id,
                    redacted_log_text(exc, limit=1000),
                )
                summary["failed"] += 1
            finally:
                summary["processed"] += 1
                heartbeat_background_worker(
                    PLAYBOOK_EXECUTION_WORKER_KIND,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary | {"last_dispatch_id": dispatch.id},
                    cycle_finished=True,
                )
        return summary

    @staticmethod
    def _empty_summary() -> dict[str, int]:
        return {
            "processed": 0,
            "completed": 0,
            "failed": 0,
            "canceled": 0,
            "interrupted": 0,
            "requeued": 0,
            "notifications": 0,
            "empty_polls": 0,
        }

    @staticmethod
    def _format_summary(summary: dict[str, int]) -> str:
        return " ".join(f"{key}={value}" for key, value in summary.items())
