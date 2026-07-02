from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, ProgrammingError

from kubernetes_ops.background_workers import KUBERNETES_OPS_SYNC_WORKER
from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.sync import KubernetesSyncResult, sync_kubernetes_providers
from servers.worker_state import (
    claim_background_worker,
    cleanup_stale_background_workers,
    heartbeat_background_worker,
    stop_background_worker,
)


class Command(BaseCommand):
    help = "Run the read-only Kubernetes Ops provider sync worker."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            help="Poll interval in seconds. Defaults to KUBERNETES_OPS_SYNC_INTERVAL_SECONDS or 300.",
        )
        parser.add_argument("--daemon", action="store_true", help="Run continuously until interrupted.")
        parser.add_argument("--once", action="store_true", help="Run one sync cycle and exit.")
        parser.add_argument("--max-runs", type=int, default=0, help="Stop after N daemon cycles. Useful for staging/tests.")
        parser.add_argument("--provider-id", type=int, default=None, help="Sync one provider by database id.")
        parser.add_argument(
            "--kind",
            choices=[K8sProvider.KIND_RANCHER, K8sProvider.KIND_DEVTRON],
            default="",
            help="Sync enabled providers of one kind.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize data without writing DB rows.")
        parser.add_argument("--lease-seconds", type=int, default=180, help="Worker heartbeat lease duration.")
        parser.add_argument("--worker-key", type=str, default="default", help="Worker instance key.")

    def handle(self, *args, **options):
        interval = self._interval_seconds(options)
        daemon = bool(options["daemon"])
        once = bool(options["once"])
        max_runs = max(0, int(options.get("max_runs") or 0))
        max_backoff_seconds = self._max_backoff_seconds(interval)
        lease_seconds = max(30, int(options.get("lease_seconds") or 180), max(interval, max_backoff_seconds) + 30)
        worker_key = str(options.get("worker_key") or "default").strip() or "default"
        provider_id = options.get("provider_id")
        kind = options.get("kind") or ""
        dry_run = bool(options.get("dry_run"))

        cleanup_stale_background_workers(KUBERNETES_OPS_SYNC_WORKER)
        state = claim_background_worker(
            KUBERNETES_OPS_SYNC_WORKER,
            worker_key=worker_key,
            command=self._command_text(daemon=daemon, interval=interval, worker_key=worker_key),
            lease_seconds=lease_seconds,
        )
        if state is None:
            self.stdout.write(self.style.WARNING(f"Kubernetes Ops sync worker {worker_key!r} is already leased by another process."))
            return

        summary = self._empty_summary(dry_run=dry_run, provider_id=provider_id, kind=kind)
        error = ""
        run_count = 0
        consecutive_failures = 0
        self.stdout.write(self.style.SUCCESS(f"Starting Kubernetes Ops sync worker ({worker_key})..."))
        try:
            while True:
                try:
                    summary = self._tick(
                        worker_key=worker_key,
                        lease_seconds=lease_seconds,
                        provider_id=provider_id,
                        kind=kind,
                        dry_run=dry_run,
                    )
                    run_count += 1
                    consecutive_failures = consecutive_failures + 1 if int(summary.get("failed") or 0) else 0
                    summary["consecutive_failures"] = consecutive_failures
                    self.stdout.write(self.style.SUCCESS(self._format_summary(summary)))
                except (OperationalError, ProgrammingError) as exc:
                    error = "Kubernetes Ops tables are not ready. Run `python manage.py migrate kubernetes_ops`."
                    self._record_cycle_error(worker_key, lease_seconds, summary, error)
                    raise CommandError(error) from exc
                except Exception as exc:
                    error = str(exc)
                    run_count += 1
                    consecutive_failures += 1
                    summary["errors"] = int(summary.get("errors") or 0) + 1
                    summary["last_error"] = error[:500]
                    summary["consecutive_failures"] = consecutive_failures
                    self._record_cycle_error(worker_key, lease_seconds, summary, error)
                    self.stderr.write(f"Kubernetes Ops sync worker cycle failed: {error}")
                    if once or not daemon:
                        raise

                if once or not daemon:
                    break
                if max_runs and run_count >= max_runs:
                    break
                delay = self._sleep_seconds(
                    interval=interval,
                    consecutive_failures=consecutive_failures,
                    max_backoff_seconds=max_backoff_seconds,
                )
                summary["next_delay_seconds"] = delay
                heartbeat_background_worker(
                    KUBERNETES_OPS_SYNC_WORKER,
                    worker_key=worker_key,
                    lease_seconds=lease_seconds,
                    summary=summary,
                )
                suffix = " with failure backoff" if consecutive_failures > 1 else ""
                self.stdout.write(f"Next Kubernetes Ops sync in {delay}s{suffix}...")
                time.sleep(delay)

            if (once or not daemon) and int(summary.get("failed") or 0):
                error = f"{summary['failed']} Kubernetes provider sync(s) failed."
                raise CommandError(error)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nKubernetes Ops sync worker stopped by user."))
        finally:
            stop_background_worker(KUBERNETES_OPS_SYNC_WORKER, worker_key=worker_key, summary=summary, error=error)

    def _tick(
        self,
        *,
        worker_key: str,
        lease_seconds: int,
        provider_id: int | None,
        kind: str,
        dry_run: bool,
    ) -> dict:
        heartbeat_background_worker(
            KUBERNETES_OPS_SYNC_WORKER,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            cycle_started=True,
        )
        results = sync_kubernetes_providers(provider_id=provider_id, kind=kind, dry_run=dry_run)
        summary = self._summarize_results(results, dry_run=dry_run, provider_id=provider_id, kind=kind)
        heartbeat_background_worker(
            KUBERNETES_OPS_SYNC_WORKER,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            summary=summary,
            cycle_finished=True,
        )
        return summary

    @staticmethod
    def _summarize_results(
        results: list[KubernetesSyncResult],
        *,
        dry_run: bool,
        provider_id: int | None,
        kind: str,
    ) -> dict:
        failed = [item for item in results if not item.success]
        return {
            "matched": len(results),
            "ok": len(results) - len(failed),
            "failed": len(failed),
            "clusters": sum(item.clusters for item in results),
            "namespaces": sum(item.namespaces for item in results),
            "workloads": sum(item.workloads for item in results),
            "pods": sum(item.pods for item in results),
            "services": sum(item.services for item in results),
            "ingresses": sum(item.ingresses for item in results),
            "events": sum(item.events for item in results),
            "apps": sum(item.apps for item in results),
            "fleet_bundles": sum(item.fleet_bundles for item in results),
            "dry_run": dry_run,
            "provider_id": provider_id,
            "kind": kind,
            "errors": len(failed),
            "last_error": (failed[-1].error[:500] if failed and failed[-1].error else ""),
            "consecutive_failures": 0,
            "next_delay_seconds": 0,
        }

    @staticmethod
    def _format_summary(summary: dict) -> str:
        return (
            f"matched={summary.get('matched', 0)} "
            f"ok={summary.get('ok', 0)} "
            f"failed={summary.get('failed', 0)} "
            f"clusters={summary.get('clusters', 0)} "
            f"namespaces={summary.get('namespaces', 0)} "
            f"workloads={summary.get('workloads', 0)} "
            f"pods={summary.get('pods', 0)} "
            f"services={summary.get('services', 0)} "
            f"ingresses={summary.get('ingresses', 0)} "
            f"events={summary.get('events', 0)} "
            f"apps={summary.get('apps', 0)} "
            f"fleet_bundles={summary.get('fleet_bundles', 0)} "
            f"dry_run={summary.get('dry_run', False)} "
            f"consecutive_failures={summary.get('consecutive_failures', 0)}"
        )

    @staticmethod
    def _record_cycle_error(worker_key: str, lease_seconds: int, summary: dict, error: str) -> None:
        heartbeat_background_worker(
            KUBERNETES_OPS_SYNC_WORKER,
            worker_key=worker_key,
            lease_seconds=lease_seconds,
            summary=summary | {"last_error": error[:500]},
            cycle_finished=True,
        )

    @staticmethod
    def _empty_summary(*, dry_run: bool, provider_id: int | None, kind: str) -> dict:
        return {
            "matched": 0,
            "ok": 0,
            "failed": 0,
            "clusters": 0,
            "namespaces": 0,
            "workloads": 0,
            "pods": 0,
            "services": 0,
            "ingresses": 0,
            "events": 0,
            "apps": 0,
            "fleet_bundles": 0,
            "dry_run": dry_run,
            "provider_id": provider_id,
            "kind": kind,
            "errors": 0,
            "last_error": "",
            "consecutive_failures": 0,
            "next_delay_seconds": 0,
        }

    @staticmethod
    def _interval_seconds(options: dict) -> int:
        configured = options.get("interval")
        if configured is None:
            configured = getattr(settings, "KUBERNETES_OPS_SYNC_INTERVAL_SECONDS", 300)
        return max(0, int(configured))

    @staticmethod
    def _max_backoff_seconds(interval: int) -> int:
        configured = getattr(settings, "KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS", 1800)
        return max(interval, int(configured or 0))

    @staticmethod
    def _sleep_seconds(*, interval: int, consecutive_failures: int, max_backoff_seconds: int) -> int:
        if interval <= 0:
            return 0
        if consecutive_failures <= 1:
            return interval
        return min(max_backoff_seconds, interval * (2 ** (consecutive_failures - 1)))

    @staticmethod
    def _command_text(*, daemon: bool, interval: int, worker_key: str) -> str:
        parts = ["python manage.py run_kubernetes_ops_sync_worker"]
        if daemon:
            parts.append("--daemon")
        parts.extend(["--interval", str(interval), "--worker-key", worker_key])
        return " ".join(parts)
