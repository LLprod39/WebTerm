"""Alert creation/resolution rules for server health monitoring.

Extracted from monitor.py to keep modules under the size limit.
Re-exported from servers.monitor for backward compatibility (tests import it there).
"""
from __future__ import annotations

from datetime import timedelta

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone

from servers.models import Server, ServerAlert
from servers.monitor_thresholds import CPU_CRIT, CPU_WARN, DISK_CRIT, DISK_WARN, MEM_CRIT, MEM_WARN


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


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
