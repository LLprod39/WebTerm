"""
SSH-based OS / distro detection for servers.

Read-only remote commands; results stored on Server.detected_os / detected_os_meta.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from django.utils import timezone
from loguru import logger

from app.tools.ssh_tools import ssh_manager
from servers.models import Server
from servers.secret_utils import get_server_auth_secret

# Matches frontend/src/lib/server-os.ts ServerOsKind (except unknown).
VALID_OS_KINDS = frozenset(
    {
        "debian",
        "ubuntu",
        "centos",
        "rhel",
        "fedora",
        "alpine",
        "arch",
        "opensuse",
        "rocky",
        "alma",
        "oracle",
        "amazon",
        "windows",
        "macos",
        "freebsd",
        "docker",
        "kubernetes",
    }
)

OS_DETECT_COMMAND = """
printf '__OS_RELEASE__\\n'
cat /etc/os-release 2>/dev/null || true
printf '\\n__UNAME__\\n'
uname -a 2>/dev/null || true
printf '\\n__BSD_VERSION__\\n'
cat /etc/version 2>/dev/null | head -3 || true
"""

_SECTION_MARKERS = ("__OS_RELEASE__", "__UNAME__", "__BSD_VERSION__")

_ID_LIKE_MAP: list[tuple[str, str]] = [
    ("ubuntu", "ubuntu"),
    ("debian", "debian"),
    ("centos", "centos"),
    ("rhel", "rhel"),
    ("redhat", "rhel"),
    ("fedora", "fedora"),
    ("rocky", "rocky"),
    ("almalinux", "alma"),
    ("alma", "alma"),
    ("oracle", "oracle"),
    ("ol", "oracle"),
    ("amzn", "amazon"),
    ("amazon", "amazon"),
    ("alpine", "alpine"),
    ("arch", "arch"),
    ("opensuse", "opensuse"),
    ("suse", "opensuse"),
    ("sles", "opensuse"),
    ("freebsd", "freebsd"),
    ("darwin", "macos"),
    ("macos", "macos"),
]


def parse_os_release(text: str) -> dict[str, str]:
    """Parse /etc/os-release KEY=VALUE lines (handles quotes)."""
    result: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().upper()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def _parse_marked_sections(raw: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {marker: [] for marker in _SECTION_MARKERS}
    current: str | None = None
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if stripped in _SECTION_MARKERS:
            current = stripped
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def _match_token(haystack: str, token: str) -> bool:
    if not haystack or not token:
        return False
    pattern = rf"(^|[\s\-_/]){re.escape(token)}([\s\-_/]|$)"
    return bool(re.search(pattern, haystack.lower()))


def map_to_os_kind(
    os_release: dict[str, str],
    *,
    uname: str = "",
    bsd_version: str = "",
) -> tuple[str, dict[str, Any]]:
    """
    Map parsed os-release + uname to a ServerOsKind string and metadata dict.
    Returns (kind, meta) where kind is a VALID_OS_KINDS member or 'unknown'.
    """
    os_id = (os_release.get("ID") or "").strip().lower()
    id_like = (os_release.get("ID_LIKE") or "").strip().lower()
    pretty = (os_release.get("PRETTY_NAME") or os_release.get("NAME") or "").strip()
    version = (os_release.get("VERSION_ID") or os_release.get("VERSION") or "").strip()
    combined = " ".join(filter(None, [os_id, id_like, pretty, uname, bsd_version])).lower()

    if "darwin" in combined or _match_token(combined, "macos"):
        kind = "macos"
    elif "freebsd" in combined:
        kind = "freebsd"
    elif any(x in combined for x in ("kubernetes", "k8s", "openshift")):
        kind = "kubernetes"
    elif "docker" in combined and "linux" not in pretty.lower():
        kind = "docker"
    else:
        kind = "unknown"
        for token, mapped in _ID_LIKE_MAP:
            if _match_token(os_id, token) or _match_token(id_like, token) or _match_token(combined, token):
                kind = mapped
                break
        if kind == "unknown" and os_id:
            if os_id in VALID_OS_KINDS:
                kind = os_id

    if kind not in VALID_OS_KINDS:
        kind = "unknown"

    meta: dict[str, Any] = {
        "id": os_id or None,
        "id_like": id_like or None,
        "version": version or None,
        "pretty_name": pretty or None,
        "uname": (uname or "").strip() or None,
        "bsd_version": (bsd_version or "").strip() or None,
        "detected_at": timezone.now().isoformat(),
    }
    return kind, meta


async def _run_detect_command(server: Server, *, secret: str, timeout_seconds: float = 15.0) -> str:
    conn_id = await ssh_manager.connect(
        host=server.host,
        username=server.username,
        password=secret or None,
        key_path=server.key_path if server.auth_method in ["key", "key_password"] else None,
        port=server.port,
        network_config=server.network_config or {},
        server=server,
    )
    try:
        result = await asyncio.wait_for(
            ssh_manager.execute(conn_id, OS_DETECT_COMMAND),
            timeout=timeout_seconds,
        )
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        return stdout if stdout.strip() else stderr
    finally:
        await ssh_manager.disconnect(conn_id)


def _mark_detection_attempt(server: Server) -> None:
    server.detected_os_attempted_at = timezone.now()
    server.save(update_fields=["detected_os_attempted_at", "updated_at"])


def _save_detection(server: Server, kind: str, meta: dict[str, Any]) -> None:
    server.detected_os = kind
    server.detected_os_meta = meta
    server.detected_os_attempted_at = timezone.now()
    server.save(
        update_fields=["detected_os", "detected_os_meta", "detected_os_attempted_at", "updated_at"]
    )


def detection_is_stale(server: Server, *, max_age_days: int = 7) -> bool:
    if not (server.detected_os or "").strip():
        return True
    meta = server.detected_os_meta if isinstance(server.detected_os_meta, dict) else {}
    detected_at = meta.get("detected_at")
    if not detected_at:
        return True
    try:
        parsed = datetime.fromisoformat(str(detected_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    except (TypeError, ValueError):
        return True
    return (timezone.now() - parsed).days >= max_age_days


async def detect_server_os(server: Server) -> dict[str, Any]:
    """Connect via SSH (or infer RDP) and persist detected OS on the server."""
    if not server.is_active:
        return {"success": False, "server_id": server.id, "error": "Server is inactive"}

    if server.is_rdp():
        meta = {
            "pretty_name": "Windows (RDP)",
            "id": "windows",
            "detected_at": timezone.now().isoformat(),
            "source": "rdp",
        }
        await sync_to_async(_save_detection)(server, "windows", meta)
        return {
            "success": True,
            "server_id": server.id,
            "detected_os": "windows",
            "detected_os_pretty": meta["pretty_name"],
            "meta": meta,
        }

    secret = await sync_to_async(get_server_auth_secret, thread_sensitive=True)(server)
    try:
        raw = await _run_detect_command(server, secret=secret)
    except Exception as exc:
        await sync_to_async(_mark_detection_attempt)(server)
        logger.debug("OS detect failed for {}: {}", server.name, exc)
        return {"success": False, "server_id": server.id, "error": str(exc)}

    sections = _parse_marked_sections(raw)
    os_release = parse_os_release(sections.get("__OS_RELEASE__", ""))
    kind, meta = map_to_os_kind(
        os_release,
        uname=sections.get("__UNAME__", ""),
        bsd_version=sections.get("__BSD_VERSION__", ""),
    )
    meta["source"] = "ssh"
    await sync_to_async(_save_detection)(server, kind, meta)
    pretty = meta.get("pretty_name") or kind
    return {
        "success": True,
        "server_id": server.id,
        "detected_os": kind,
        "detected_os_pretty": pretty,
        "meta": meta,
    }


async def detect_os_batch(servers: list[Server], *, concurrency: int = 4) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(max(1, min(concurrency, 8)))

    async def _one(item: Server) -> dict[str, Any]:
        async with sem:
            return await detect_server_os(item)

    return await asyncio.gather(*[_one(s) for s in servers])
