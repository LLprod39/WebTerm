"""
Server health monitoring service.

Connects to servers via SSH and collects system metrics
(CPU, RAM, disk, load, uptime, process count) on a schedule.
Deep checks additionally scan for failed services and log errors.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import timedelta
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async as _s2a
from django.conf import settings


def sync_to_async(func, thread_sensitive=False):
    """Wrapper that defaults thread_sensitive=False to avoid CurrentThreadExecutor conflicts."""
    return _s2a(func, thread_sensitive=thread_sensitive)
from django.utils import timezone
from loguru import logger

from servers.models import Server, ServerAlert, ServerHealthCheck
from servers.secret_utils import get_server_auth_secret
from servers.ssh_host_keys import build_server_connect_kwargs, ensure_server_known_hosts

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
CPU_WARN = 80.0
CPU_CRIT = 95.0
MEM_WARN = 85.0
MEM_CRIT = 95.0
DISK_WARN = 80.0
DISK_CRIT = 90.0


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


def _parse_loadavg(line: str) -> tuple[float, float, float]:
    parts = line.strip().split()
    if len(parts) >= 3:
        return float(parts[0]), float(parts[1]), float(parts[2])
    return 0.0, 0.0, 0.0


def _parse_free(line: str) -> tuple[int, int, float]:
    """Parse 'Mem:  total  used  free ...' -> (total_mb, used_mb, percent)."""
    parts = line.strip().split()
    if len(parts) >= 3:
        total = int(parts[1])
        used = int(parts[2])
        pct = round(used / total * 100, 1) if total > 0 else 0.0
        return total, used, pct
    return 0, 0, 0.0


def _parse_df(line: str) -> tuple[float, float, float]:
    """Parse df output -> (total_gb, used_gb, percent)."""
    parts = line.strip().split()
    if len(parts) >= 5:
        pct_str = parts[4].rstrip("%")
        try:
            pct = float(pct_str)
        except ValueError:
            pct = 0.0
        total = _size_to_gb(parts[1])
        used = _size_to_gb(parts[2])
        return total, used, pct
    return 0.0, 0.0, 0.0


def _size_to_gb(s: str) -> float:
    s = s.strip().upper()
    try:
        if s.endswith("T"):
            return float(s[:-1]) * 1024
        if s.endswith("G"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1024
        if s.endswith("K"):
            return float(s[:-1]) / (1024 * 1024)
        return float(s) / (1024 * 1024 * 1024)
    except ValueError:
        return 0.0


def _parse_uptime(line: str) -> int:
    parts = line.strip().split()
    if parts:
        try:
            return int(float(parts[0]))
        except ValueError:
            pass
    return 0


def _parse_quick_output(raw: str) -> dict[str, Any]:
    lines = [l for l in raw.strip().splitlines() if l.strip()]
    result: dict[str, Any] = {}

    for line in lines:
        stripped = line.strip()
        if re.match(r"^\d+\.\d+\s+\d+\.\d+\s+\d+\.\d+", stripped):
            l1, l5, l15 = _parse_loadavg(stripped)
            result["load_1m"] = l1
            result["load_5m"] = l5
            result["load_15m"] = l15
        elif stripped.startswith("Mem:"):
            total, used, pct = _parse_free(stripped)
            result["memory_total_mb"] = total
            result["memory_used_mb"] = used
            result["memory_percent"] = pct
        elif "%" in stripped and ("/" in stripped or "G" in stripped.upper() or "M" in stripped.upper()):
            total, used, pct = _parse_df(stripped)
            result["disk_total_gb"] = total
            result["disk_used_gb"] = used
            result["disk_percent"] = pct
        elif re.match(r"^\d+(\.\d+)?\s+\d+(\.\d+)?$", stripped):
            result["uptime_seconds"] = _parse_uptime(stripped)
        elif re.match(r"^\d+$", stripped):
            val = int(stripped)
            if "uptime_seconds" not in result and val > 100:
                result["uptime_seconds"] = val
            else:
                result["process_count"] = val
        elif stripped.startswith("NET_RX_BYTES="):
            try:
                result["net_rx_bytes"] = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                pass
        elif stripped.startswith("NET_TX_BYTES="):
            try:
                result["net_tx_bytes"] = int(stripped.split("=", 1)[1].strip())
            except ValueError:
                pass

    if "load_1m" in result:
        result["cpu_percent"] = min(round(result["load_1m"] * 100 / max(_get_cpu_estimate(result), 1), 1), 100.0)
    return result


def _get_cpu_estimate(parsed: dict) -> int:
    """Rough CPU count estimate based on load context (default 1)."""
    return 1


def _determine_status(metrics: dict[str, Any]) -> str:
    cpu = metrics.get("cpu_percent", 0)
    mem = metrics.get("memory_percent", 0)
    disk = metrics.get("disk_percent", 0)

    if cpu >= CPU_CRIT or mem >= MEM_CRIT or disk >= DISK_CRIT:
        return ServerHealthCheck.STATUS_CRITICAL
    if cpu >= CPU_WARN or mem >= MEM_WARN or disk >= DISK_WARN:
        return ServerHealthCheck.STATUS_WARNING
    return ServerHealthCheck.STATUS_HEALTHY


def _parse_deep_output(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {"failed_services": [], "log_errors": [], "kernel_errors": []}
    section = "services"
    for line in raw.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "UNIT" in stripped and "LOAD" in stripped:
            continue
        if "-- No entries --" in stripped or "-- Journal begins" in stripped:
            continue

        if "failed" in stripped.lower() and ("loaded" in stripped.lower() or ".service" in stripped):
            result["failed_services"].append(stripped.split()[0] if stripped.split() else stripped)
        elif any(k in stripped.lower() for k in ["error", "err", "crit", "alert", "emerg", "fail"]):
            if section == "services":
                section = "logs"
            if section == "logs":
                result["log_errors"].append(stripped[:200])
            else:
                result["kernel_errors"].append(stripped[:200])

    return result


def _parse_docker_output(raw: str) -> dict[str, Any]:
    containers: list[dict[str, str]] = []
    problem_containers: list[dict[str, str]] = []
    for line in raw.strip().splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        name, state, status = (part.strip() for part in stripped.split("|", 2))
        if not name:
            continue
        row = {
            "name": name,
            "state": state.lower(),
            "status": status,
        }
        containers.append(row)
        lowered_status = status.lower()
        if row["state"] != "running" or "unhealthy" in lowered_status:
            problem_containers.append(row)
    return {
        "containers": containers,
        "problem_containers": problem_containers,
    }


async def _create_alerts(server: Server, metrics: dict, deep_data: dict | None = None) -> None:
    now = timezone.now()
    recent_window = now - timedelta(minutes=15)

    async def _alert_exists(alert_type: str, fingerprint: str = "") -> bool:
        def _exists() -> bool:
            rows = ServerAlert.objects.filter(
                server=server,
                alert_type=alert_type,
                is_resolved=False,
                created_at__gte=recent_window,
            ).only("metadata")
            if not fingerprint:
                return rows.exists()
            for row in rows:
                metadata = row.metadata if isinstance(row.metadata, dict) else {}
                if str(metadata.get("fingerprint") or "") == fingerprint:
                    return True
            return False

        return await sync_to_async(_exists)()

    async def _create(
        alert_type: str,
        severity: str,
        title: str,
        message: str = "",
        meta: dict | None = None,
        *,
        fingerprint: str = "",
    ):
        if await _alert_exists(alert_type, fingerprint):
            return
        payload = dict(meta or {})
        if fingerprint:
            payload["fingerprint"] = fingerprint
        await sync_to_async(ServerAlert.objects.create)(
            server=server,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            metadata=payload,
        )

    async def _resolve_stale_docker_alerts(active_fingerprints: set[str]) -> None:
        def _resolve() -> None:
            rows = list(
                ServerAlert.objects.filter(
                    server=server,
                    alert_type=ServerAlert.TYPE_SERVICE,
                    is_resolved=False,
                ).only("id", "metadata", "is_resolved", "resolved_at")
            )
            for row in rows:
                metadata = row.metadata if isinstance(row.metadata, dict) else {}
                if str(metadata.get("service_kind") or "") != "docker_container":
                    continue
                fingerprint = str(metadata.get("fingerprint") or "").strip()
                if not fingerprint.startswith("docker-down:"):
                    continue
                if fingerprint in active_fingerprints:
                    continue
                row.is_resolved = True
                row.resolved_at = now
                row.save(update_fields=["is_resolved", "resolved_at"])

        await sync_to_async(_resolve)()

    cpu = metrics.get("cpu_percent", 0)
    mem = metrics.get("memory_percent", 0)
    disk = metrics.get("disk_percent", 0)

    if cpu >= CPU_CRIT:
        await _create(ServerAlert.TYPE_CPU, ServerAlert.SEVERITY_CRITICAL, f"CPU {cpu}%", f"Load: {metrics.get('load_1m', '?')}")
    elif cpu >= CPU_WARN:
        await _create(ServerAlert.TYPE_CPU, ServerAlert.SEVERITY_WARNING, f"CPU {cpu}%", f"Load: {metrics.get('load_1m', '?')}")

    if mem >= MEM_CRIT:
        await _create(ServerAlert.TYPE_MEMORY, ServerAlert.SEVERITY_CRITICAL, f"RAM {mem}%", f"{metrics.get('memory_used_mb', '?')}MB / {metrics.get('memory_total_mb', '?')}MB")
    elif mem >= MEM_WARN:
        await _create(ServerAlert.TYPE_MEMORY, ServerAlert.SEVERITY_WARNING, f"RAM {mem}%", f"{metrics.get('memory_used_mb', '?')}MB / {metrics.get('memory_total_mb', '?')}MB")

    if disk >= DISK_CRIT:
        await _create(ServerAlert.TYPE_DISK, ServerAlert.SEVERITY_CRITICAL, f"Disk {disk}%", f"{metrics.get('disk_used_gb', '?')}GB / {metrics.get('disk_total_gb', '?')}GB")
    elif disk >= DISK_WARN:
        await _create(ServerAlert.TYPE_DISK, ServerAlert.SEVERITY_WARNING, f"Disk {disk}%", f"{metrics.get('disk_used_gb', '?')}GB / {metrics.get('disk_total_gb', '?')}GB")

    if deep_data:
        failed = deep_data.get("failed_services", [])
        if failed:
            await _create(
                ServerAlert.TYPE_SERVICE,
                ServerAlert.SEVERITY_CRITICAL,
                f"Обнаружены упавшие systemd-сервисы: {len(failed)}",
                "\n".join(failed[:10]),
                {
                    "services": failed[:20],
                    "service_kind": "systemd",
                },
                fingerprint="systemd-failed-services",
            )

        log_errors = deep_data.get("log_errors", [])
        kernel_errors = deep_data.get("kernel_errors", [])
        all_errors = log_errors + kernel_errors
        if all_errors:
            await _create(
                ServerAlert.TYPE_LOG_ERROR,
                ServerAlert.SEVERITY_WARNING,
                f"Найдены ошибки в логах: {len(all_errors)}",
                "\n".join(all_errors[:10]),
                {"errors": all_errors[:30]},
                fingerprint="monitor-log-errors",
            )

        docker_data = deep_data.get("docker") if isinstance(deep_data.get("docker"), dict) else {}
        problem_containers = docker_data.get("problem_containers", []) if isinstance(docker_data, dict) else []
        active_docker_fingerprints: set[str] = set()
        if problem_containers:
            container_names = [str(item.get("name") or "").strip() for item in problem_containers if str(item.get("name") or "").strip()]
            fingerprint = "docker-down:" + ",".join(sorted(container_names))
            active_docker_fingerprints.add(fingerprint)
            await _create(
                ServerAlert.TYPE_SERVICE,
                ServerAlert.SEVERITY_CRITICAL,
                f"Docker-контейнер недоступен: {', '.join(container_names[:3])}",
                "\n".join(
                    f"{item.get('name')}: {item.get('status') or item.get('state')}"
                    for item in problem_containers[:10]
                ),
                {
                    "service_kind": "docker_container",
                    "containers": problem_containers,
                    "container_name": container_names[0] if container_names else "",
                },
                fingerprint=fingerprint,
            )
        await _resolve_stale_docker_alerts(active_docker_fingerprints)


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
            title=f"Server unreachable",
            message=error_msg[:500],
        )
    return health


async def check_all_servers(
    deep: bool = False,
    concurrency: int = 5,
    server_ids: list[int] | None = None,
) -> list[ServerHealthCheck]:
    """Check all active SSH servers with limited concurrency."""
    normalized_ids = sorted({int(item) for item in (server_ids or []) if str(item).strip().isdigit()})

    def _load_servers() -> list[Server]:
        qs = Server.objects.filter(is_active=True, server_type="ssh")
        if normalized_ids:
            qs = qs.filter(id__in=normalized_ids)
        return list(qs.order_by("id"))

    servers = await sync_to_async(_load_servers)()

    if not servers:
        logger.info("Monitor: no active SSH servers to check")
        return []

    sem = asyncio.Semaphore(concurrency)
    results: list[ServerHealthCheck] = []

    async def _check(srv: Server):
        async with sem:
            hc = await check_server(srv, deep=deep)
            if hc:
                results.append(hc)

    await asyncio.gather(*[_check(s) for s in servers], return_exceptions=True)
    return results


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
