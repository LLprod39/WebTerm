"""Live fleet metrics streamed over persistent SSH sessions.

F-08a.10: line parsing helpers live in ``monitoring_live_parse``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

import asyncssh
from channels.layers import get_channel_layer
from django.conf import settings
from loguru import logger

from servers.monitoring.monitoring_live_parse import (
    REMOTE_LOOP_TEMPLATE,
    compute_cpu_percent,
    parse_live_line,
)
from servers.services.pilot_destination_policy import validate_pilot_ssh_destination

__all__ = [
    "REMOTE_LOOP_TEMPLATE",
    "LiveMetricsManager",
    "compute_cpu_percent",
    "fetch_live_samples",
    "live_cache_key",
    "live_group_name",
    "monitoring_endpoint_key",
    "parse_live_line",
    "store_live_samples",
]


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


def _live_cache_ttl_seconds() -> int:
    """How long the last live sample stays available after the stream stops.

    Background monitor only persists full metrics every ~60s. Live is faster but
    was not stored — after a page reload the UI only saw the DB snapshot and looked
    "old". Caching the last live tick bridges reload / short tab switches.
    """
    # 5 minutes: enough for dashboard navigation without flashing "нет связи".
    return max(30, int(getattr(settings, "MONITORING_LIVE_CACHE_SECONDS", 300) or 300))


def live_cache_key(server_id: int) -> str:
    return f"monitoring:live:last:{int(server_id)}"


def _live_redis_client():
    """Shared Redis so ASGI live writers and HTTP status readers share samples.

    Falls back to None (caller uses Django cache) when Redis is unavailable.
    """
    import os

    url = (
        (getattr(settings, "CHANNEL_REDIS_URL", None) or "")
        or (getattr(settings, "CELERY_BROKER_URL", None) or "")
        or os.environ.get("CHANNEL_REDIS_URL", "")
        or os.environ.get("CELERY_BROKER_URL", "")
        or os.environ.get("REDIS_URL", "")
    ).strip()
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def store_live_samples(server_ids: list[int], payload: dict) -> None:
    """Persist last live sample for HTTP status reads (Redis preferred)."""
    if not server_ids:
        return

    sample = {
        "cpu_percent": payload.get("cpu_percent"),
        "memory_percent": payload.get("memory_percent"),
        "disk_percent": payload.get("disk_percent"),
        "load_1m": payload.get("load_1m"),
        "ts": float(payload.get("ts") or time.time()),
    }
    # Skip incomplete frames (no usable metric).
    if all(sample.get(k) is None for k in ("cpu_percent", "memory_percent", "disk_percent")):
        return
    ttl = _live_cache_ttl_seconds()

    client = _live_redis_client()
    if client is not None:
        import json

        pipe = client.pipeline()
        body = json.dumps(sample)
        for sid in server_ids:
            pipe.set(live_cache_key(sid), body, ex=ttl)
        with contextlib.suppress(Exception):
            pipe.execute()
            return

    # Dev fallback: process-local Django cache (same process only).
    with contextlib.suppress(Exception):
        from django.core.cache import cache

        cache.set_many({live_cache_key(sid): sample for sid in server_ids}, timeout=ttl)


def fetch_live_samples(server_ids: list[int]) -> dict[int, dict]:
    """Return cached live samples keyed by server_id (may be empty)."""
    if not server_ids:
        return {}

    client = _live_redis_client()
    if client is not None:
        import json

        keys = [live_cache_key(int(sid)) for sid in server_ids]
        try:
            values = client.mget(keys)
        except Exception:
            # The writer falls back to Django cache when Redis is configured
            # but temporarily unavailable.  Readers must take the same path;
            # returning here would make a successful fallback write invisible.
            values = None
        if values is not None:
            out: dict[int, dict] = {}
            for sid, raw in zip(server_ids, values, strict=False):
                if not raw:
                    continue
                with contextlib.suppress(TypeError, ValueError, json.JSONDecodeError):
                    value = json.loads(raw)
                    if isinstance(value, dict) and value.get("ts"):
                        out[int(sid)] = value
            return out

    with contextlib.suppress(Exception):
        from django.core.cache import cache

        keys = {int(sid): live_cache_key(int(sid)) for sid in server_ids}
        raw = cache.get_many(list(keys.values()))
        out = {}
        for sid, key in keys.items():
            value = raw.get(key)
            if isinstance(value, dict) and value.get("ts"):
                out[sid] = value
        return out
    return {}


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

    async def _inventory_server_ids(self, entry: _CollectorEntry) -> list[int]:
        """All inventory rows for this physical endpoint (for cache fan-out)."""
        from servers.models import Server
        from servers.monitoring.monitor import sync_to_async

        def _load():
            return list(
                Server.objects.filter(
                    is_active=True,
                    server_type="ssh",
                    host__iexact=entry.host,
                    port=entry.port,
                ).values_list("id", flat=True)
            )

        ids = await sync_to_async(_load)()
        return sorted({int(sid) for sid in ids})

    async def _broadcast_to_servers(self, server_ids: list[int], payload: dict) -> None:
        channel_layer = get_channel_layer()
        if channel_layer is None or not server_ids:
            return
        for server_id in server_ids:
            event = {**payload, "server_id": server_id}
            with contextlib.suppress(Exception):
                await channel_layer.group_send(live_group_name(server_id), event)

    async def _publish_live_sample(self, entry: _CollectorEntry, payload: dict) -> None:
        """WS fan-out to active subscribers + cache for HTTP status / reload."""
        from servers.monitoring.monitor import sync_to_async

        active_ids = self._active_server_ids(entry)
        cache_ids = active_ids
        # Prefer caching under every inventory row for this host:port so a reload
        # of any user's server list still sees the fresh sample.
        with contextlib.suppress(Exception):
            inventory_ids = await self._inventory_server_ids(entry)
            if inventory_ids:
                cache_ids = inventory_ids
        with contextlib.suppress(Exception):
            await sync_to_async(store_live_samples)(cache_ids, payload)
        if active_ids:
            await self._broadcast_to_servers(active_ids, payload)

    async def _broadcast_state(self, entry: _CollectorEntry, state: str, error: str = "") -> None:
        await self._broadcast_to_servers(
            self._active_server_ids(entry),
            {"type": "live.state", "state": state, "error": error[:300]},
        )

    async def _resolve_endpoint(self, server_id: int) -> tuple[str, str, int] | None:
        from servers.models import Server
        from servers.monitoring.monitor import sync_to_async

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
        from servers.monitoring.monitor import sync_to_async

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
                preferred = set(preferred_ids)
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
        from servers.monitoring.monitor import _build_connect_kwargs

        kwargs = await _build_connect_kwargs(server)
        command = REMOTE_LOOP_TEMPLATE.format(interval=interval)
        prev_sample: dict | None = None

        validate_pilot_ssh_destination(server.host, server.port)
        async with asyncssh.connect(**kwargs) as conn, conn.create_process(command) as process:
            await self._broadcast_state(entry, "streaming")
            while not self._should_stop(entry, started_at):
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=interval * 5)
                except TimeoutError:
                    continue
                if not line:
                    raise ConnectionError("live metrics stream ended")
                sample = parse_live_line(line)
                if sample is None:
                    continue
                # CPU needs two /proc/stat ticks. Seed prev and skip the first
                # incomplete frame so clients don't flash RAM/disk without CPU
                # (or wipe a full DB snapshot with a partial live override).
                if prev_sample is None:
                    prev_sample = sample
                    continue
                cpu_percent = compute_cpu_percent(prev_sample, sample)
                prev_sample = sample
                await self._publish_live_sample(
                    entry,
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
