"""Live fleet metrics streamed over persistent SSH sessions.

While at least one browser subscribes to a server, a single collector task
holds one SSH connection and runs a tiny remote loop that prints /proc-based
metrics every few seconds. Samples are fanned out to all subscribers through
the Channels layer and are never written to the database — the periodic
run_monitor worker remains the source of persisted history.

Collectors are keyed by host:port, not inventory row id. If two users add the
same physical host, exactly one SSH session streams metrics and both server
rows receive the same live samples under their own server_id.

The manager is per-process: with a single ASGI process (the default
deployment) exactly one SSH session exists per watched endpoint regardless of
how many operators have the servers page open.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import asyncssh
from channels.layers import get_channel_layer
from django.conf import settings
from loguru import logger


def live_group_name(server_id: int) -> str:
    return f"monitoring_live_{int(server_id)}"


def monitoring_endpoint_key(host: str, port: int | str | None) -> str:
    """Stable key for a physical SSH endpoint shared across inventory rows."""
    normalized_host = (host or "").strip().lower()
    try:
        normalized_port = int(port or 22)
    except (TypeError, ValueError):
        normalized_port = 22
    return f"{normalized_host}:{normalized_port}"


def _live_interval_seconds() -> int:
    return min(10, max(1, int(getattr(settings, "MONITORING_LIVE_INTERVAL_SECONDS", 2) or 2)))


def _live_grace_seconds() -> float:
    return max(0.0, float(getattr(settings, "MONITORING_LIVE_GRACE_SECONDS", 15) or 0))


def _live_max_lifetime_seconds() -> int:
    return max(60, int(getattr(settings, "MONITORING_LIVE_MAX_LIFETIME_SECONDS", 3600) or 3600))


# One echo line per tick; reading /proc costs microseconds on the target host.
REMOTE_LOOP_TEMPLATE = (
    "while :; do "
    "cpu=$(head -n1 /proc/stat); "
    'load=$(cut -d" " -f1-3 /proc/loadavg); '
    "mem=$(awk '/^MemTotal:/{{t=$2}} /^MemAvailable:/{{a=$2}} END{{print t\" \"a}}' /proc/meminfo); "
    "disk=$(df -P / 2>/dev/null | awk 'NR==2{{gsub(\"%\",\"\",$5); print $5}}'); "
    'echo "LIVE|$cpu|$load|$mem|$disk"; '
    "sleep {interval}; "
    "done"
)


def parse_live_line(line: str) -> dict | None:
    """Parse one `LIVE|<cpu>|<load>|<mem>|<disk>` sample line."""
    parts = line.strip().split("|")
    if len(parts) != 5 or parts[0] != "LIVE":
        return None

    cpu_fields = parts[1].split()
    if not cpu_fields or cpu_fields[0] != "cpu":
        return None
    try:
        ticks = [int(value) for value in cpu_fields[1:]]
    except ValueError:
        return None
    if len(ticks) < 4:
        return None
    # user nice system idle iowait ... — idle time includes iowait.
    idle_ticks = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)

    load_fields = parts[2].split()
    load_1m = None
    if load_fields:
        with contextlib.suppress(ValueError):
            load_1m = float(load_fields[0])

    memory_percent = None
    mem_fields = parts[3].split()
    if len(mem_fields) == 2:
        with contextlib.suppress(ValueError, ZeroDivisionError):
            total_kb = float(mem_fields[0])
            available_kb = float(mem_fields[1])
            if total_kb > 0:
                memory_percent = round((total_kb - available_kb) / total_kb * 100, 1)

    disk_percent = None
    if parts[4].strip():
        with contextlib.suppress(ValueError):
            disk_percent = float(parts[4].strip())

    return {
        "cpu_total_ticks": sum(ticks),
        "cpu_idle_ticks": idle_ticks,
        "load_1m": load_1m,
        "memory_percent": memory_percent,
        "disk_percent": disk_percent,
    }


def compute_cpu_percent(prev: dict, current: dict) -> float | None:
    """CPU usage between two /proc/stat samples; None until two ticks exist."""
    delta_total = current["cpu_total_ticks"] - prev["cpu_total_ticks"]
    delta_idle = current["cpu_idle_ticks"] - prev["cpu_idle_ticks"]
    if delta_total <= 0:
        return None
    usage = (1 - delta_idle / delta_total) * 100
    return round(max(0.0, min(100.0, usage)), 1)


class _CollectorEntry:
    __slots__ = ("endpoint_key", "refcount", "task", "idle_since", "server_refcounts", "host", "port")

    def __init__(self, endpoint_key: str, host: str, port: int):
        self.endpoint_key = endpoint_key
        self.host = host
        self.port = port
        self.refcount = 0
        self.task: asyncio.Task | None = None
        self.idle_since: float | None = None
        # inventory server_id -> active WS subscriptions for that row
        self.server_refcounts: dict[int, int] = {}


class LiveMetricsManager:
    """Refcounted collectors keyed by host:port (one SSH session per endpoint)."""

    def __init__(self):
        self._entries: dict[str, _CollectorEntry] = {}
        self._server_to_endpoint: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, server_id: int) -> None:
        server_id = int(server_id)
        endpoint = await self._resolve_endpoint(server_id)
        if endpoint is None:
            return
        endpoint_key, host, port = endpoint

        async with self._lock:
            entry = self._entries.get(endpoint_key)
            if entry is None or entry.task is None or entry.task.done():
                entry = _CollectorEntry(endpoint_key, host, port)
                self._entries[endpoint_key] = entry
                entry.task = asyncio.create_task(self._run_collector(entry))
            entry.server_refcounts[server_id] = entry.server_refcounts.get(server_id, 0) + 1
            entry.refcount += 1
            entry.idle_since = None
            self._server_to_endpoint[server_id] = endpoint_key

    async def unsubscribe(self, server_id: int) -> None:
        server_id = int(server_id)
        async with self._lock:
            endpoint_key = self._server_to_endpoint.get(server_id)
            if not endpoint_key:
                return
            entry = self._entries.get(endpoint_key)
            if entry is None:
                self._server_to_endpoint.pop(server_id, None)
                return

            remaining = entry.server_refcounts.get(server_id, 0) - 1
            if remaining <= 0:
                entry.server_refcounts.pop(server_id, None)
                self._server_to_endpoint.pop(server_id, None)
            else:
                entry.server_refcounts[server_id] = remaining

            entry.refcount = max(0, entry.refcount - 1)
            if entry.refcount == 0:
                entry.idle_since = time.monotonic()

    def _should_stop(self, entry: _CollectorEntry, started_at: float) -> bool:
        if time.monotonic() - started_at > _live_max_lifetime_seconds():
            return True
        if entry.refcount > 0 or entry.idle_since is None:
            return False
        return time.monotonic() - entry.idle_since >= _live_grace_seconds()

    def _active_server_ids(self, entry: _CollectorEntry) -> list[int]:
        return sorted(server_id for server_id, count in entry.server_refcounts.items() if count > 0)

    async def _broadcast_to_servers(self, server_ids: list[int], payload: dict) -> None:
        channel_layer = get_channel_layer()
        if channel_layer is None or not server_ids:
            return
        for server_id in server_ids:
            event = {**payload, "server_id": server_id}
            with contextlib.suppress(Exception):
                await channel_layer.group_send(live_group_name(server_id), event)

    async def _broadcast_state(self, entry: _CollectorEntry, state: str, error: str = "") -> None:
        await self._broadcast_to_servers(
            self._active_server_ids(entry),
            {"type": "live.state", "state": state, "error": error[:300]},
        )

    async def _resolve_endpoint(self, server_id: int) -> tuple[str, str, int] | None:
        from servers.models import Server
        from servers.monitor import sync_to_async

        def _load():
            return (
                Server.objects.filter(id=server_id, is_active=True, server_type="ssh")
                .values_list("host", "port")
                .first()
            )

        row = await sync_to_async(_load)()
        if not row:
            return None
        host = (row[0] or "").strip()
        if not host:
            return None
        try:
            port = int(row[1] or 22)
        except (TypeError, ValueError):
            port = 22
        return monitoring_endpoint_key(host, port), host, port

    async def _pick_connection_server(self, entry: _CollectorEntry):
        """Pick an inventory row to open SSH with (prefer currently subscribed rows)."""
        from servers.models import Server
        from servers.monitor import sync_to_async

        preferred_ids = self._active_server_ids(entry)

        def _load():
            qs = Server.objects.filter(
                is_active=True,
                server_type="ssh",
                host__iexact=entry.host,
                port=entry.port,
            ).order_by("id")
            servers = list(qs)
            if not servers:
                return None
            if preferred_ids:
                preferred = {sid for sid in preferred_ids}
                ordered = [s for s in servers if s.id in preferred] + [s for s in servers if s.id not in preferred]
                return ordered
            return servers

        return await sync_to_async(_load)()

    async def _run_collector(self, entry: _CollectorEntry) -> None:
        started_at = time.monotonic()
        interval = _live_interval_seconds()
        attempts = 0

        try:
            while not self._should_stop(entry, started_at):
                candidates = await self._pick_connection_server(entry)
                if not candidates:
                    await self._broadcast_state(entry, "stopped", "Server not available")
                    return

                attempts += 1
                await self._broadcast_state(entry, "connecting")
                last_error: Exception | None = None
                connected = False
                for server in candidates:
                    try:
                        await self._stream_from_server(server, entry, started_at, interval)
                        return  # clean stop (no subscribers / lifetime cap)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        last_error = exc
                        logger.debug(
                            "Monitor live: stream for {} via server_id={} failed: {}",
                            entry.endpoint_key,
                            server.id,
                            exc,
                        )
                        continue

                if not connected:
                    await self._broadcast_state(entry, "error", str(last_error or "connection failed"))
                    if attempts >= 3:
                        return
                    for _ in range(10):
                        if self._should_stop(entry, started_at):
                            return
                        await asyncio.sleep(0.5)
        finally:
            async with self._lock:
                if self._entries.get(entry.endpoint_key) is entry:
                    del self._entries[entry.endpoint_key]
                for server_id, mapped in list(self._server_to_endpoint.items()):
                    if mapped == entry.endpoint_key and server_id not in entry.server_refcounts:
                        self._server_to_endpoint.pop(server_id, None)
            await self._broadcast_state(entry, "stopped")

    async def _stream_from_server(
        self,
        server,
        entry: _CollectorEntry,
        started_at: float,
        interval: int,
    ) -> None:
        from servers.monitor import _build_connect_kwargs

        kwargs = await _build_connect_kwargs(server)
        command = REMOTE_LOOP_TEMPLATE.format(interval=interval)
        prev_sample: dict | None = None

        async with asyncssh.connect(**kwargs) as conn, conn.create_process(command) as process:
            await self._broadcast_state(entry, "streaming")
            while not self._should_stop(entry, started_at):
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=interval * 5)
                except asyncio.TimeoutError:
                    continue
                if not line:
                    raise ConnectionError("live metrics stream ended")
                sample = parse_live_line(line)
                if sample is None:
                    continue
                cpu_percent = compute_cpu_percent(prev_sample, sample) if prev_sample else None
                prev_sample = sample
                await self._broadcast_to_servers(
                    self._active_server_ids(entry),
                    {
                        "type": "live.metrics",
                        "cpu_percent": cpu_percent,
                        "memory_percent": sample["memory_percent"],
                        "disk_percent": sample["disk_percent"],
                        "load_1m": sample["load_1m"],
                        "ts": time.time(),
                    },
                )


live_metrics_manager = LiveMetricsManager()
