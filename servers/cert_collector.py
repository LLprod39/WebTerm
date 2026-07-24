"""TLS certificate inventory collector.

Discovers listening TCP ports on a server over SSH and performs local TLS
handshakes against 127.0.0.1 with the server's public hostname as SNI, so
certificates are inventoried even when the WebTerm host cannot reach the
port through a firewall. STARTTLS-only services (SMTP, IMAP, LDAP) are not
probed by this version.
"""

from __future__ import annotations

import asyncio
import re
import shlex
from datetime import UTC, datetime
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from servers.models import Server, ServerCertificate

CERT_MARKER_RE = re.compile(r"^==WTCERT:([A-Z0-9]+)==$")
_SAN_ENTRY_RE = re.compile(r"(?:DNS|IP Address):([^,\s]+)")
_MAX_PORTS = 20


def sync_to_async(func, thread_sensitive=True):
    return _s2a(func, thread_sensitive=thread_sensitive)


def build_cert_script(server_host: str, ssh_port: int) -> str:
    """POSIX-sh command that prints one ==WTCERT:<port>== block per TLS port."""
    sni = shlex.quote((server_host or "localhost").strip() or "localhost")
    port_pipeline = "sed 's/.*://' | grep -E '^[0-9]+$' | sort -un | grep -xv \"$SSHP\" | head -" + str(_MAX_PORTS)
    parts = [
        f"SNI={sni}",
        f"SSHP={int(ssh_port or 22)}",
        "TMO=$(command -v timeout >/dev/null 2>&1 && echo 'timeout 6' || echo '')",
        "PORTS=$(ss -tlnH 2>/dev/null | awk '{print $4}' | " + port_pipeline + ")",
        "if [ -z \"$PORTS\" ]; then PORTS=$(netstat -tln 2>/dev/null | awk 'NR>2 {print $4}' | "
        + port_pipeline
        + "); fi",
        "if command -v openssl >/dev/null 2>&1; then "
        "for p in $PORTS; do "
        'pem=$($TMO openssl s_client -connect "127.0.0.1:$p" -servername "$SNI" </dev/null 2>/dev/null '
        "| sed -n '/BEGIN CERTIFICATE/,/END CERTIFICATE/p'); "
        'if [ -n "$pem" ]; then '
        'echo "==WTCERT:$p=="; '
        "printf '%s\\n' \"$pem\" | openssl x509 -noout -subject -issuer -serial -startdate -enddate -fingerprint -sha256 2>/dev/null; "
        "printf '%s\\n' \"$pem\" | openssl x509 -noout -ext subjectAltName 2>/dev/null; "
        "fi; "
        "done; "
        'else echo "==WTCERT:NOOPENSSL=="; fi',
        'echo "==WTCERT:END=="',
    ]
    return "; ".join(parts)


def _parse_openssl_date(value: str) -> datetime | None:
    normalized = " ".join(value.strip().split())
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_cert_block(port: int, lines: list[str]) -> dict[str, Any]:
    cert: dict[str, Any] = {"port": port, "sans": []}
    in_san = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered.startswith("subject="):
            cert["subject"] = stripped.partition("=")[2].strip()
        elif lowered.startswith("issuer="):
            cert["issuer"] = stripped.partition("=")[2].strip()
        elif lowered.startswith("serial="):
            cert["serial"] = stripped.partition("=")[2].strip()
        elif lowered.startswith("notbefore="):
            cert["not_before"] = _parse_openssl_date(stripped.partition("=")[2])
        elif lowered.startswith("notafter="):
            cert["not_after"] = _parse_openssl_date(stripped.partition("=")[2])
        elif "fingerprint=" in lowered:
            cert["fingerprint_sha256"] = stripped.rpartition("=")[2].strip().upper()
        elif "subject alternative name" in lowered:
            in_san = True
        elif in_san:
            entries = _SAN_ENTRY_RE.findall(stripped)
            if entries:
                cert["sans"].extend(entries)
            else:
                in_san = False
    return cert


def parse_cert_output(raw: str) -> tuple[list[dict[str, Any]], bool]:
    """Parse collector output -> (certificates, scan_completed)."""
    blocks: dict[int, list[str]] = {}
    current_port: int | None = None
    completed = False
    openssl_missing = False

    for line in (raw or "").splitlines():
        stripped = line.strip()
        match = CERT_MARKER_RE.fullmatch(stripped)
        if match:
            token = match.group(1)
            if token == "END":
                completed = True
                current_port = None
            elif token == "NOOPENSSL":
                openssl_missing = True
                current_port = None
            elif token.isdigit():
                current_port = int(token)
                blocks.setdefault(current_port, [])
            else:
                current_port = None
            continue
        if current_port is not None:
            blocks[current_port].append(line)

    certs = [_parse_cert_block(port, lines) for port, lines in sorted(blocks.items())]
    certs = [cert for cert in certs if cert.get("fingerprint_sha256") or cert.get("subject")]
    if openssl_missing:
        completed = False
    return certs, completed


def upsert_certificates(
    server: Server,
    certs: list[dict[str, Any]],
    *,
    scan_completed: bool,
    now: datetime | None = None,
) -> dict[str, int]:
    """Idempotent write of parsed certificates; deactivates vanished ports."""
    now = now or timezone.now()
    seen_ports: set[int] = set()
    created = updated = changed = 0

    for cert in certs:
        port = int(cert["port"])
        seen_ports.add(port)
        fingerprint = str(cert.get("fingerprint_sha256") or "")
        defaults = {
            "endpoint": f"{(server.host or '').strip()}:{port}",
            "subject": str(cert.get("subject") or ""),
            "issuer": str(cert.get("issuer") or ""),
            "serial": str(cert.get("serial") or "")[:128],
            "fingerprint_sha256": fingerprint[:128],
            "not_before": cert.get("not_before"),
            "not_after": cert.get("not_after"),
            "sans": list(cert.get("sans") or [])[:50],
            "is_active": True,
            "last_seen_at": now,
            "last_checked_at": now,
        }
        row = ServerCertificate.objects.filter(server=server, source=ServerCertificate.SOURCE_LISTEN, port=port).first()
        if row is None:
            ServerCertificate.objects.create(
                server=server,
                source=ServerCertificate.SOURCE_LISTEN,
                port=port,
                **defaults,
            )
            created += 1
            continue

        if fingerprint and row.fingerprint_sha256 and fingerprint != row.fingerprint_sha256:
            row.previous_fingerprint = row.fingerprint_sha256
            row.fingerprint_changed_at = now
            changed += 1
        for field, value in defaults.items():
            setattr(row, field, value)
        row.save()
        updated += 1

    deactivated = 0
    if scan_completed:
        deactivated = (
            ServerCertificate.objects.filter(server=server, source=ServerCertificate.SOURCE_LISTEN, is_active=True)
            .exclude(port__in=seen_ports)
            .update(is_active=False, last_checked_at=now)
        )

    return {
        "found": len(certs),
        "created": created,
        "updated": updated,
        "changed": changed,
        "deactivated": deactivated,
    }


async def collect_server_certificates(server: Server) -> dict[str, int] | None:
    """Scan one server; returns an upsert summary or None when skipped/failed."""
    if server.server_type != "ssh" or not server.is_active:
        return None

    from servers.monitor import _build_connect_kwargs

    try:
        kwargs = await _build_connect_kwargs(server)
        async with asyncssh.connect(**kwargs) as conn:
            script = build_cert_script(server.host, int(server.port or 22))
            result = await asyncio.wait_for(conn.run(script, check=False), timeout=90)
    except Exception as exc:
        logger.debug("Cert collector: SSH failed for {}: {}", server.name, exc)
        return None

    certs, completed = parse_cert_output(result.stdout or "")
    summary = await sync_to_async(upsert_certificates)(server, certs, scan_completed=completed)
    logger.info(
        "Cert collector: {} -> {} cert(s), {} changed, {} deactivated",
        server.name,
        summary["found"],
        summary["changed"],
        summary["deactivated"],
    )
    return summary


async def collect_certificates_for_all(
    *,
    concurrency: int = 3,
    server_ids: list[int] | None = None,
) -> dict[str, int]:
    """Scan active SSH servers with limited concurrency."""

    def _load_servers() -> list[Server]:
        qs = Server.objects.filter(is_active=True, server_type="ssh")
        if server_ids:
            qs = qs.filter(id__in=server_ids)
        return list(qs.order_by("id"))

    servers = await sync_to_async(_load_servers)()
    if not servers:
        return {"servers": 0, "scanned": 0, "certificates": 0}

    sem = asyncio.Semaphore(max(1, concurrency))
    totals = {"servers": len(servers), "scanned": 0, "certificates": 0}

    async def _scan(server: Server) -> None:
        async with sem:
            summary = await collect_server_certificates(server)
            if summary is not None:
                totals["scanned"] += 1
                totals["certificates"] += summary["found"]

    await asyncio.gather(*[_scan(server) for server in servers], return_exceptions=True)
    return totals
