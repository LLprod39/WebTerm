"""
Server health monitoring service.

Connects to servers via SSH and collects system metrics
(CPU, RAM, disk, load, uptime, process count) on a schedule.
Deep checks additionally scan for failed services and log errors.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import timedelta
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async as _s2a
from django.conf import settings
from django.utils import timezone
from loguru import logger

from servers.models import Server, ServerAlert, ServerHealthCheck
from servers.monitor_parsing import (
    _parse_deep_output,
    _parse_docker_output,
    _parse_quick_output,
)
from servers.secret_utils import get_server_auth_secret
from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts

# Alert rules live in monitor_alerts (split for size limits); re-exported for tests.
from servers.monitor_alerts import _create_alerts  # noqa: F401


def sync_to_async(func, thread_sensitive=False):
    """Wrapper that defaults thread_sensitive=False to avoid CurrentThreadExecutor conflicts."""
    return _s2a(func, thread_sensitive=thread_sensitive)


QUICK_COMMANDS = (
    "cat /proc/loadavg;"
    "free -m | grep Mem;"
    "df -h / | tail -1;"
    "cat /proc/uptime;"
    "ps aux --no-headers 2>/dev/null | wc -l;"
    "cat /proc/net/dev 2>/dev/null | awk 'NR>2 {rx+=$2; tx+=$10} END {print \"NET_RX_BYTES=\" rx; print \"NET_TX_BYTES=\" tx}' || true"
)

DEEP_COMMANDS = (
    "systemctl list-units --state=failed --no-pager --plain 2>/dev/null || true;"
    "journalctl -p 3 --since '10 minutes ago' --no-pager -q 2>/dev/null | tail -30 || true;"
    "dmesg --level=err,crit -T 2>/dev/null | tail -20 || true"
)
DOCKER_MONITOR_COMMAND = "docker ps -a --format '{{.Names}}|{{.State}}|{{.Status}}' 2>/dev/null || true"

# Thresholds
# Thresholds shared with monitor_alerts; single source in monitor_thresholds.
from servers.monitor_thresholds import (  # noqa: E402, F401
    CPU_CRIT,
    CPU_WARN,
    DISK_CRIT,
    DISK_WARN,
    MEM_CRIT,
    MEM_WARN,
)


def _decrypt_server_secret(server: Server) -> str:
    return get_server_auth_secret(server)


async def _build_connect_kwargs(server: Server) -> dict[str, Any]:
    known_hosts = await ensure_server_known_hosts(server)
    secret = await sync_to_async(_decrypt_server_secret, thread_sensitive=True)(server)
    return build_server_connect_kwargs(
        server,
        secret=secret,
        known_hosts=known_hosts,
        connect_timeout=max(1, int(getattr(settings, "SSH_CONNECT_TIMEOUT_SECONDS", 10) or 10)),
        login_timeout=max(1, int(getattr(settings, "SSH_LOGIN_TIMEOUT_SECONDS", 20) or 20)),
    )


def _determine_status(metrics: dict[str, Any]) -> str:
    cpu = metrics.get("cpu_percent", 0)
    mem = metrics.get("memory_percent", 0)
    disk = metrics.get("disk_percent", 0)

    if cpu >= CPU_CRIT or mem >= MEM_CRIT or disk >= DISK_CRIT:
        return ServerHealthCheck.STATUS_CRITICAL
    if cpu >= CPU_WARN or mem >= MEM_WARN or disk >= DISK_WARN:
        return ServerHealthCheck.STATUS_WARNING
    return ServerHealthCheck.STATUS_HEALTHY


async def probe_server_lite(server: Server) -> ServerHealthCheck | None:
    """TCP reachability probe (no SSH login, no metrics)."""
    if not server.is_active:
        return None

    host = (server.host or "").strip()
    if not host:
        return await _save_unreachable(server, "Empty host", 0)

    port = int(server.port or 22)

    timeout = max(1.0, float(getattr(settings, "MONITORING_LITE_CHECK_TIMEOUT_SECONDS", 5) or 5))
    t0 = time.monotonic()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.debug("Monitor lite: {}:{} unreachable: {}", host, port, exc)
        return await _save_unreachable(server, str(exc), elapsed)

    elapsed = int((time.monotonic() - t0) * 1000)

    def _reuse_recent_ok_check() -> ServerHealthCheck | None:
        latest = ServerHealthCheck.objects.filter(server=server).order_by("-checked_at").first()
        if not latest or latest.status == ServerHealthCheck.STATUS_UNREACHABLE:
            return None
        stale_seconds = max(60, int(getattr(settings, "MONITORING_STATUS_STALE_SECONDS", 300) or 300))
        if latest.checked_at and (timezone.now() - latest.checked_at).total_seconds() <= stale_seconds:
            return latest
        return None

    existing = await sync_to_async(_reuse_recent_ok_check)()
    if existing:
        return existing

    return await sync_to_async(ServerHealthCheck.objects.create)(
        server=server,
        status=ServerHealthCheck.STATUS_HEALTHY,
        response_time_ms=elapsed,
        is_deep=False,
        raw_output={"lite": True, "probe": "tcp", "port": port},
    )


async def check_server(server: Server, deep: bool = False) -> ServerHealthCheck | None:
    """Run health check on a single server. Returns the created HealthCheck or None on error."""
    if server.server_type != "ssh":
        return None

    t0 = time.monotonic()
    try:
        kwargs = await _build_connect_kwargs(server)
    except Exception as exc:
        logger.debug("Monitor: cannot build connect kwargs for {}: {}", server.name, exc)
        return await _save_unreachable(server, str(exc))

    cmd = QUICK_COMMANDS
    if deep:
        cmd += ";" + DEEP_COMMANDS

    try:
        async with asyncssh.connect(**kwargs) as conn:
            result = await asyncio.wait_for(conn.run(cmd, check=False), timeout=30)
            raw = result.stdout or ""
            docker_raw = ""
            if deep:
                docker_result = await asyncio.wait_for(conn.run(DOCKER_MONITOR_COMMAND, check=False), timeout=20)
                docker_raw = docker_result.stdout or ""
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.debug("Monitor: SSH failed for {}: {}", server.name, exc)
        return await _save_unreachable(server, str(exc), elapsed)

    elapsed = int((time.monotonic() - t0) * 1000)

    metrics = _parse_quick_output(raw)
    deep_data = _parse_deep_output(raw) if deep else None
    if deep:
        docker_data = _parse_docker_output(docker_raw)
        if deep_data is None:
            deep_data = {}
        deep_data["docker"] = docker_data

    status = _determine_status(metrics)
    raw_output = {"quick": raw}
    if deep_data:
        raw_output["deep"] = deep_data

    health = await sync_to_async(ServerHealthCheck.objects.create)(
        server=server,
        status=status,
        cpu_percent=metrics.get("cpu_percent"),
        memory_percent=metrics.get("memory_percent"),
        memory_used_mb=metrics.get("memory_used_mb"),
        memory_total_mb=metrics.get("memory_total_mb"),
        disk_percent=metrics.get("disk_percent"),
        disk_used_gb=metrics.get("disk_used_gb"),
        disk_total_gb=metrics.get("disk_total_gb"),
        load_1m=metrics.get("load_1m"),
        load_5m=metrics.get("load_5m"),
        load_15m=metrics.get("load_15m"),
        uptime_seconds=metrics.get("uptime_seconds"),
        process_count=metrics.get("process_count"),
        response_time_ms=elapsed,
        is_deep=deep,
        raw_output=raw_output,
    )

    await _create_alerts(server, metrics, deep_data)

    from servers.os_detect_service import (
        os_detect_cooldown_allows,
        schedule_os_detect_for_server_ids,
        server_needs_os_detect,
    )

    if server_needs_os_detect(server) and os_detect_cooldown_allows(server):
        schedule_os_detect_for_server_ids([server.id])

    logger.info(
        "Monitor: {} -> {} (cpu={}, mem={}, disk={}, {}ms)",
        server.name, status,
        metrics.get("cpu_percent", "?"), metrics.get("memory_percent", "?"),
        metrics.get("disk_percent", "?"), elapsed,
    )
    return health


async def _save_unreachable(server: Server, error_msg: str, elapsed_ms: int = 0) -> ServerHealthCheck:
    health = await sync_to_async(ServerHealthCheck.objects.create)(
        server=server,
        status=ServerHealthCheck.STATUS_UNREACHABLE,
        response_time_ms=elapsed_ms,
        raw_output={"error": error_msg[:500]},
    )

    now = timezone.now()
    recent = now - timedelta(minutes=15)
    exists = await sync_to_async(
        lambda: ServerAlert.objects.filter(
            server=server,
            alert_type=ServerAlert.TYPE_UNREACHABLE,
            is_resolved=False,
            created_at__gte=recent,
        ).exists()
    )()
    if not exists:
        await sync_to_async(ServerAlert.objects.create)(
            server=server,
            alert_type=ServerAlert.TYPE_UNREACHABLE,
            severity=ServerAlert.SEVERITY_CRITICAL,
            title="Server unreachable",
            message=error_msg[:500],
        )
    return health


def _monitoring_endpoint_key(server: Server) -> str:
    host = (server.host or "").strip().lower()
    try:
        port = int(server.port or 22)
    except (TypeError, ValueError):
        port = 22
    return f"{host}:{port}"


async def _mirror_health_check(
    source: ServerHealthCheck,
    target_servers: list[Server],
) -> list[ServerHealthCheck]:
    """Copy a health snapshot onto sibling inventory rows for the same host:port."""
    if not target_servers:
        return []

    raw = dict(source.raw_output) if isinstance(source.raw_output, dict) else {}
    raw["mirrored_from_server_id"] = source.server_id

    def _create_all() -> list[ServerHealthCheck]:
        rows: list[ServerHealthCheck] = []
        for target in target_servers:
            if target.id == source.server_id:
                continue
            rows.append(
                ServerHealthCheck.objects.create(
                    server=target,
                    status=source.status,
                    cpu_percent=source.cpu_percent,
                    memory_percent=source.memory_percent,
                    memory_used_mb=source.memory_used_mb,
                    memory_total_mb=source.memory_total_mb,
                    disk_percent=source.disk_percent,
                    disk_used_gb=source.disk_used_gb,
                    disk_total_gb=source.disk_total_gb,
                    load_1m=source.load_1m,
                    load_5m=source.load_5m,
                    load_15m=source.load_15m,
                    uptime_seconds=source.uptime_seconds,
                    process_count=source.process_count,
                    response_time_ms=source.response_time_ms,
                    is_deep=source.is_deep,
                    raw_output=raw,
                )
            )
        return rows

    return await sync_to_async(_create_all)()


async def _check_endpoint_group(
    servers: list[Server],
    *,
    deep: bool,
    use_lite: bool,
) -> list[ServerHealthCheck]:
    """Probe one physical endpoint and mirror status onto all inventory rows."""
    if not servers:
        return []

    results: list[ServerHealthCheck] = []
    # Non-SSH or lite: TCP once, then mirror.
    if use_lite or any(s.server_type != "ssh" for s in servers):
        primary = servers[0]
        hc = await probe_server_lite(primary)
        if hc:
            results.append(hc)
            # probe_server_lite may reuse a recent check without creating a new row;
            # still mirror a fresh snapshot for siblings so every row has current status.
            if hc.status == ServerHealthCheck.STATUS_UNREACHABLE or not getattr(hc, "id", None):
                mirrored = await _mirror_health_check(hc, servers[1:])
                results.extend(mirrored)
            else:
                # Fresh or reused OK probe: ensure siblings get the same status.
                mirrored = await _mirror_health_check(hc, servers[1:])
                results.extend(mirrored)
        return results

    # SSH: try credentials from each inventory row until one succeeds, then mirror.
    last_hc: ServerHealthCheck | None = None
    for candidate in servers:
        hc = await check_server(candidate, deep=deep)
        if not hc:
            continue
        results.append(hc)
        last_hc = hc
        if hc.status != ServerHealthCheck.STATUS_UNREACHABLE:
            siblings = [s for s in servers if s.id != candidate.id]
            results.extend(await _mirror_health_check(hc, siblings))
            return results

    # All candidates unreachable: mirror the last failure onto remaining rows that
    # did not get their own check (if we only tried some before giving up — we try all).
    if last_hc is not None:
        already = {hc.server_id for hc in results if getattr(hc, "server_id", None)}
        remaining = [s for s in servers if s.id not in already]
        results.extend(await _mirror_health_check(last_hc, remaining))
    return results


async def check_all_servers(
    deep: bool = False,
    lite: bool = False,
    concurrency: int = 5,
    server_ids: list[int] | None = None,
) -> list[ServerHealthCheck]:
    """Check active servers with limited concurrency.

    lite=True runs TCP reachability only (quick fleet sweep).
    deep=True runs full SSH metrics + optional deep diagnostics.
    Non-SSH servers always get a TCP reachability probe.

    Inventory rows that share the same host:port are treated as one physical
    endpoint: only one probe runs and the resulting status is mirrored to every
    user-owned server row so each list shows the correct current health.
    """
    normalized_ids = sorted({int(item) for item in (server_ids or []) if str(item).strip().isdigit()})
    use_lite = bool(lite and not deep)

    def _load_servers() -> list[Server]:
        qs = Server.objects.filter(is_active=True)
        if normalized_ids:
            qs = qs.filter(id__in=normalized_ids)
        return list(qs.order_by("id"))

    servers = await sync_to_async(_load_servers)()

    if not servers:
        logger.info("Monitor: no active servers to check")
        return []

    groups: dict[str, list[Server]] = {}
    for server in servers:
        groups.setdefault(_monitoring_endpoint_key(server), []).append(server)

    logger.info(
        "Monitor: checking {} inventory rows as {} unique endpoint(s)",
        len(servers),
        len(groups),
    )

    sem = asyncio.Semaphore(concurrency)
    results: list[ServerHealthCheck] = []

    async def _check_group(group: list[Server]):
        async with sem:
            group_results = await _check_endpoint_group(group, deep=deep, use_lite=use_lite)
            results.extend(group_results)

    await asyncio.gather(*[_check_group(group) for group in groups.values()], return_exceptions=True)
    return results


def schedule_health_check_for_server_ids(server_ids: list[int], *, deep: bool = False) -> None:
    """Fire-and-forget health check after a server is added (does not block HTTP)."""
    import threading

    ids = sorted({int(item) for item in server_ids if item})
    if not ids:
        return

    def _worker() -> None:
        try:
            from asgiref.sync import async_to_sync

            async_to_sync(check_all_servers)(deep=deep, lite=False, server_ids=ids, concurrency=1)
        except Exception as exc:
            logger.debug("Background health check for servers {} failed: {}", ids, exc)

    threading.Thread(target=_worker, daemon=True, name="monitor-server-bootstrap").start()


async def cleanup_old_data(days: int = 7) -> None:
    """Remove health checks and resolved alerts older than N days."""
    cutoff = timezone.now() - timedelta(days=days)
    deleted_hc = await sync_to_async(
        lambda: ServerHealthCheck.objects.filter(checked_at__lt=cutoff).delete()
    )()
    deleted_alerts = await sync_to_async(
        lambda: ServerAlert.objects.filter(is_resolved=True, created_at__lt=cutoff).delete()
    )()
    logger.info("Monitor cleanup: removed {} health checks, {} resolved alerts", deleted_hc[0], deleted_alerts[0])
