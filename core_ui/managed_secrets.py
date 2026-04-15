from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from core_ui.models import ManagedSecret

SERVER_AUTH_NAMESPACE = "server_auth_secret"
MCP_ENV_NAMESPACE = "mcp_secret_env"


class ManagedSecretError(RuntimeError):
    pass


def _build_fernet() -> Fernet:
    seed = (
        os.getenv("MANAGED_SECRET_KEY")
        or os.getenv("APP_SECRET_ENCRYPTION_KEY")
        or settings.SECRET_KEY
    )
    digest = hashlib.sha256(f"{seed}:managed-secret:v1".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _build_fernet().encrypt(raw).decode("utf-8")


def _decrypt_payload(ciphertext: str) -> Any:
    try:
        raw = _build_fernet().decrypt((ciphertext or "").encode("utf-8"))
    except InvalidToken as exc:
        raise ManagedSecretError("Managed secret cannot be decrypted with the current server key") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ManagedSecretError("Managed secret payload is corrupted") from exc


def _upsert(namespace: str, object_id: int, payload: Any, *, key: str = "default", metadata: dict | None = None) -> ManagedSecret:
    secret, _ = ManagedSecret.objects.update_or_create(
        namespace=namespace,
        object_id=int(object_id),
        key=key,
        defaults={
            "ciphertext": _encrypt_payload(payload),
            "metadata": metadata or {},
        },
    )
    return secret


def _get(namespace: str, object_id: int, *, key: str = "default", default: Any = None) -> Any:
    secret = ManagedSecret.objects.filter(namespace=namespace, object_id=int(object_id), key=key).first()
    if not secret:
        return default
    return _decrypt_payload(secret.ciphertext)


def _has(namespace: str, object_id: int, *, key: str = "default") -> bool:
    return ManagedSecret.objects.filter(namespace=namespace, object_id=int(object_id), key=key).exists()


def _delete(namespace: str, object_id: int, *, key: str = "default") -> None:
    ManagedSecret.objects.filter(namespace=namespace, object_id=int(object_id), key=key).delete()


def set_server_auth_secret(server_id: int, secret_value: str) -> None:
    value = (secret_value or "").strip()
    if not value:
        _delete(SERVER_AUTH_NAMESPACE, server_id)
        return
    _upsert(
        SERVER_AUTH_NAMESPACE,
        server_id,
        {"secret": value},
        metadata={"kind": "server_auth"},
    )


def get_server_auth_secret(server_id: int) -> str:
    payload = _get(SERVER_AUTH_NAMESPACE, server_id, default={})
    if isinstance(payload, dict):
        return str(payload.get("secret") or "")
    return ""


def has_server_auth_secret(server_id: int) -> bool:
    return _has(SERVER_AUTH_NAMESPACE, server_id)


def set_mcp_secret_env(mcp_id: int, env: dict[str, str] | None) -> None:
    data = {str(k): str(v) for k, v in (env or {}).items() if str(k).strip()}
    if not data:
        _delete(MCP_ENV_NAMESPACE, mcp_id)
        return
    _upsert(
        MCP_ENV_NAMESPACE,
        mcp_id,
        data,
        metadata={"keys": sorted(data.keys()), "kind": "mcp_env"},
    )


def get_mcp_secret_env(mcp_id: int) -> dict[str, str]:
    payload = _get(MCP_ENV_NAMESPACE, mcp_id, default={})
    if isinstance(payload, dict):
        return {str(k): str(v) for k, v in payload.items()}
    return {}


def get_mcp_secret_env_keys(mcp_id: int) -> list[str]:
    secret = ManagedSecret.objects.filter(namespace=MCP_ENV_NAMESPACE, object_id=int(mcp_id), key="default").first()
    if not secret:
        return []
    keys = secret.metadata.get("keys") if isinstance(secret.metadata, dict) else []
    if isinstance(keys, list) and keys:
        return [str(item) for item in keys]
    return sorted(get_mcp_secret_env(mcp_id).keys())


def has_mcp_secret_env(mcp_id: int) -> bool:
    return _has(MCP_ENV_NAMESPACE, mcp_id)
