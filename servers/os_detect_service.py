"""
Scheduling, cooldown, and background execution for automatic OS detection.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from loguru import logger

from servers.models import Server
from servers.os_detect import detect_os_batch, detect_server_os, detection_is_stale

FAILURE_COOLDOWN = timedelta(hours=24)
SUCCESS_RECHECK_COOLDOWN = timedelta(days=7)
BOOTSTRAP_MAX_SERVERS = 15


def server_needs_os_detect(server: Server) -> bool:
    if not server.is_active:
        return False
    if (server.server_type or "ssh").lower() != "ssh":
        return False
    if not (server.detected_os or "").strip():
        return True
    return detection_is_stale(server)


def os_detect_cooldown_allows(server: Server, *, force: bool = False) -> bool:
    if force:
        return True
    attempted_at = server.detected_os_attempted_at
    if not attempted_at:
        return True
    now = timezone.now()
    if (server.detected_os or "").strip() and not detection_is_stale(server):
        return False
    cooldown = SUCCESS_RECHECK_COOLDOWN if (server.detected_os or "").strip() else FAILURE_COOLDOWN
    return (now - attempted_at) >= cooldown


def filter_servers_for_auto_detect(servers: list[Server], *, force: bool = False) -> list[Server]:
    return [s for s in servers if server_needs_os_detect(s) and os_detect_cooldown_allows(s, force=force)]


def detect_os_for_server(server_id: int, *, force: bool = False) -> dict[str, Any]:
    """Run OS detection for one server with lock + cooldown (used by API and jobs)."""
    server = Server.objects.filter(id=server_id, is_active=True).first()
    if not server:
        return {"success": False, "server_id": server_id, "error": "Server not found"}

    if not force and not os_detect_cooldown_allows(server):
        return {
            "success": True,
            "cached": True,
            "server_id": server.id,
            "detected_os": (server.detected_os or "").strip(),
        }

    if not force and not server_needs_os_detect(server):
        return {
            "success": True,
            "cached": True,
            "server_id": server.id,
            "detected_os": (server.detected_os or "").strip(),
        }

    lock_timeout_seconds = max(15, int(getattr(settings, "OS_DETECT_LOCK_SECONDS", 30) or 30))
    lock_key = f"servers:os-detect:lock:{server.id}"
    if not cache.add(lock_key, "1", timeout=lock_timeout_seconds):
        return {"success": True, "queued": True, "server_id": server.id}

    try:
        return async_to_sync(detect_server_os)(server)
    finally:
        cache.delete(lock_key)


def schedule_os_detect_for_server_ids(server_ids: list[int], *, force: bool = False) -> None:
    """Fire-and-forget batch OS detection (does not block HTTP responses)."""
    ids = sorted({int(item) for item in server_ids if item})
    if not ids:
        return

    def _worker() -> None:
        try:
            servers = list(Server.objects.filter(id__in=ids, is_active=True))
            targets = filter_servers_for_auto_detect(servers, force=force)
            if not targets:
                return
            concurrency = max(1, min(int(getattr(settings, "OS_DETECT_CONCURRENCY", 4) or 4), 5))
            async_to_sync(detect_os_batch)(targets, concurrency=concurrency)
        except Exception as exc:
            logger.debug("Background OS detect batch failed: {}", exc)

    threading.Thread(target=_worker, daemon=True, name="os-detect-batch").start()


def schedule_os_detect_after_bootstrap(servers: list[Server]) -> None:
    """Enqueue detection for stale/unknown servers when SPA loads bootstrap (capped)."""
    targets = filter_servers_for_auto_detect(servers)[:BOOTSTRAP_MAX_SERVERS]
    if targets:
        schedule_os_detect_for_server_ids([s.id for s in targets])
