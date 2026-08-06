from __future__ import annotations

import signal
import subprocess
import sys
import time
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError


@dataclass
class _WorkerSpec:
    name: str
    args: list[str]
    process: subprocess.Popen[str] | None = None
    restarts: int = 0


class Command(BaseCommand):
    help = (
        "Supervise long-running ops workers: memory dreams, execution plane, scheduled agents, and optional watchers."
    )

    def add_arguments(self, parser):
        parser.add_argument("--with-watchers", action="store_true", help="Also supervise the watchers worker")
        parser.add_argument(
            "--with-scheduled-agents", action="store_true", help="Also supervise scheduled server agents"
        )
        parser.add_argument(
            "--without-agent-execution",
            action="store_true",
            help="Do not start the legacy single agent worker when a dedicated scalable pool is deployed",
        )
        parser.add_argument(
            "--restart-delay", type=int, default=5, help="Seconds to wait before restarting a dead worker"
        )
        parser.add_argument(
            "--lease-seconds", type=int, default=180, help="Lease heartbeat duration passed to child workers"
        )
        parser.add_argument(
            "--dream-interval", type=int, default=300, help="Poll interval for run_memory_dreams --daemon"
        )
        parser.add_argument(
            "--execution-interval", type=int, default=5, help="Poll interval for run_agent_execution_plane"
        )
        parser.add_argument(
            "--scheduled-agents-interval", type=int, default=60, help="Poll interval for run_scheduled_agents"
        )
        parser.add_argument("--scheduled-agents-limit", type=int, default=100, help="Scheduled agents batch limit")
        parser.add_argument("--watchers-interval", type=int, default=120, help="Poll interval for run_watchers")
        parser.add_argument("--watchers-limit", type=int, default=100, help="Watcher batch limit")
        parser.add_argument("--once", action="store_true", help="Run each worker once and exit")

    def handle(self, *args, **options):
        once = bool(options["once"])
        restart_delay = max(1, int(options["restart_delay"] or 5))
        lease_seconds = max(30, int(options["lease_seconds"] or 180))
        worker_specs = self._build_specs(options, lease_seconds=lease_seconds, once=once)
        stop_requested = False

        def _request_stop(*_args):
            nonlocal stop_requested
            stop_requested = True

        previous_handlers: dict[int, object] = {}
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is None:
                continue
            try:
                previous_handlers[sig] = signal.signal(sig, _request_stop)
            except (ValueError, OSError):
                continue

        self.stdout.write(self.style.SUCCESS("Starting ops supervisor..."))
        try:
            for spec in worker_specs:
                self._start_worker(spec)

            if once:
                failed_workers: list[tuple[str, int]] = []
                for spec in worker_specs:
                    code = spec.process.wait() if spec.process is not None else 0
                    self.stdout.write(f"[{spec.name}] exited with code {code}")
                    if int(code or 0) != 0:
                        failed_workers.append((spec.name, int(code or 0)))
                if failed_workers:
                    details = ", ".join(f"{name}={code}" for name, code in failed_workers)
                    raise CommandError(f"Ops supervisor workers failed: {details}")
                return

            while not stop_requested:
                for spec in worker_specs:
                    process = spec.process
                    if process is None:
                        continue
                    code = process.poll()
                    if code is None:
                        continue
                    spec.restarts += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{spec.name}] exited with code {code}; restarting in {restart_delay}s (restart #{spec.restarts})"
                        )
                    )
                    time.sleep(restart_delay)
                    if stop_requested:
                        break
                    self._start_worker(spec)
                time.sleep(1)
        finally:
            for spec in worker_specs:
                self._stop_worker(spec)
            for sig, handler in previous_handlers.items():
                try:
                    signal.signal(sig, handler)
                except (ValueError, OSError):
                    continue

    def _build_specs(self, options, *, lease_seconds: int, once: bool) -> list[_WorkerSpec]:
        base = [sys.executable, "manage.py"]
        specs = [
            _WorkerSpec(
                name="memory_dreams",
                args=base
                + [
                    "run_memory_dreams",
                    *(
                        ["--once"]
                        if once
                        else ["--daemon", "--interval", str(max(60, int(options["dream_interval"] or 300)))]
                    ),
                    "--lease-seconds",
                    str(lease_seconds),
                ],
            ),
        ]
        if not bool(options.get("without_agent_execution")):
            specs.append(
                _WorkerSpec(
                    name="agent_execution",
                    args=base
                    + [
                        "run_agent_execution_plane",
                        *(["--once"] if once else ["--interval", str(max(2, int(options["execution_interval"] or 5)))]),
                        "--worker-key",
                        "default",
                        "--lease-seconds",
                        str(lease_seconds),
                    ],
                )
            )
        if bool(options.get("with_scheduled_agents")):
            specs.append(
                _WorkerSpec(
                    name="scheduled_agents",
                    args=base
                    + [
                        "run_scheduled_agents",
                        *(
                            ["--once"]
                            if once
                            else [
                                "--daemon",
                                "--interval",
                                str(max(15, int(options["scheduled_agents_interval"] or 60))),
                            ]
                        ),
                        "--worker-key",
                        "default",
                        "--lease-seconds",
                        str(lease_seconds),
                        "--limit",
                        str(max(1, min(int(options["scheduled_agents_limit"] or 100), 500))),
                    ],
                )
            )
        if bool(options.get("with_watchers")):
            specs.append(
                _WorkerSpec(
                    name="watchers",
                    args=base
                    + [
                        "run_watchers",
                        *(
                            ["--once"]
                            if once
                            else ["--daemon", "--interval", str(max(30, int(options["watchers_interval"] or 120)))]
                        ),
                        "--lease-seconds",
                        str(lease_seconds),
                        "--limit",
                        str(max(1, min(int(options["watchers_limit"] or 100), 500))),
                    ],
                )
            )
        return specs

    def _start_worker(self, spec: _WorkerSpec):
        self.stdout.write(f"Starting [{spec.name}] -> {' '.join(spec.args)}")
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        spec.process = subprocess.Popen(
            spec.args,
            text=True,
            cwd=".",
            creationflags=creationflags,
        )

    def _stop_worker(self, spec: _WorkerSpec):
        process = spec.process
        if process is None:
            return
        if process.poll() is not None:
            return
        self.stdout.write(f"Stopping [{spec.name}]...")
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
