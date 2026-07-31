"""Safe hashes that bind a run to the validated server connection identity."""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from core_ui.managed_secrets import SERVER_AUTH_NAMESPACE, SERVER_SUDO_NAMESPACE
from core_ui.models import ManagedSecret


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _value_fingerprint(value: Any) -> str:
    if value in (None, "", b"", {}, []):
        return ""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    return _hash_payload(value)


def _key_file_revision(key_path: str) -> dict[str, Any]:
    path = str(key_path or "").strip()
    if not path:
        return {"path_fingerprint": "", "state": "not_configured"}
    revision: dict[str, Any] = {
        "path_fingerprint": hashlib.sha256(path.encode("utf-8")).hexdigest(),
        "state": "unavailable",
    }
    try:
        stat = os.stat(path)
    except OSError:
        return revision
    revision.update(
        {
            "state": "available",
            "size": int(stat.st_size),
            "modified_ns": int(stat.st_mtime_ns),
        }
    )
    return revision


def _managed_secret_revisions(server_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    revisions: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if not server_ids:
        return revisions
    rows = ManagedSecret.objects.filter(
        namespace__in=[SERVER_AUTH_NAMESPACE, SERVER_SUDO_NAMESPACE],
        object_id__in=server_ids,
    ).order_by("object_id", "namespace", "key")
    for row in rows:
        revisions[int(row.object_id)].append(
            {
                "id": row.id,
                "namespace": row.namespace,
                "key": row.key,
                "updated_at": row.updated_at.isoformat(),
                # Ciphertext is never returned or persisted. Its digest makes
                # same-record credential rotation part of the revision.
                "ciphertext_fingerprint": hashlib.sha256(row.ciphertext.encode("utf-8")).hexdigest(),
            }
        )
    return revisions


def target_connection_identity_hashes(servers: Iterable[Any]) -> dict[str, str]:
    """Return only per-server hashes; no credential or network value escapes."""

    ordered = sorted(servers, key=lambda item: int(item.id))
    server_ids = [int(server.id) for server in ordered]
    managed_revisions = _managed_secret_revisions(server_ids)
    identities: dict[str, str] = {}
    for server in ordered:
        connection_payload = {
            "server_type": str(getattr(server, "server_type", "") or "ssh"),
            "host": str(getattr(server, "host", "") or "").strip().lower(),
            "port": int(getattr(server, "port", 22) or 22),
            "username": str(getattr(server, "username", "") or ""),
            "auth_method": str(getattr(server, "auth_method", "") or ""),
            "sudo_auth_mode": str(getattr(server, "sudo_auth_mode", "") or ""),
            "active": bool(getattr(server, "is_active", False)),
            "network_fingerprint": _hash_payload(
                {
                    "config": getattr(server, "network_config", {}) or {},
                    "corporate_context": str(getattr(server, "corporate_context", "") or ""),
                    "has_proxy": bool(getattr(server, "has_proxy", False)),
                    "requires_vpn": bool(getattr(server, "requires_vpn", False)),
                    "behind_firewall": bool(getattr(server, "behind_firewall", False)),
                }
            ),
            "trusted_host_key_fingerprint": _hash_payload(getattr(server, "trusted_host_keys", []) or []),
            "credential_revision": _hash_payload(
                {
                    "managed": managed_revisions.get(int(server.id), []),
                    "key_file": _key_file_revision(getattr(server, "key_path", "")),
                }
            ),
        }
        identities[str(server.id)] = _hash_payload(connection_payload)
    return identities


def target_connection_identities_match(
    expected: Any,
    servers: Iterable[Any],
) -> bool:
    if not isinstance(expected, dict):
        return False
    normalized = {str(key): str(value) for key, value in expected.items() if str(key).isdigit() and str(value).strip()}
    return normalized == target_connection_identity_hashes(servers)
