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
SERVER_SUDO_NAMESPACE = "server_sudo_secret"
MCP_ENV_NAMESPACE = "mcp_secret_env"
LLM_API_KEY_NAMESPACE = "llm_api_key"
LLM_API_KEY_OBJECT_ID = 1
NOTIFICATION_SECRET_NAMESPACE = "notification_secret"
NOTIFICATION_SECRET_OBJECT_ID = 1
KUBERNETES_PROVIDER_TOKEN_NAMESPACE = "kubernetes_provider_token"
PLAYBOOK_BINDING_VARIABLES_NAMESPACE = "playbook_binding_variables"
PLAYBOOK_RUN_VARIABLES_NAMESPACE = "playbook_run_variables"
PLAYBOOK_RUN_MASTER_PASSWORD_NAMESPACE = "playbook_run_master_password"
STUDIO_PIPELINE_SECRETS_NAMESPACE = "studio_pipeline_secrets"
LLM_API_KEY_PROVIDERS = {
    "gemini": "GEMINI_API_KEY",
    "grok": "GROK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": "OLLAMA_API_KEY",
}


class ManagedSecretError(RuntimeError):
    pass


def allow_secret_key_fallback() -> bool:
    return (os.getenv("ALLOW_SECRET_KEY_MANAGED_ENCRYPTION", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def uses_dedicated_managed_secret_key() -> bool:
    return bool((os.getenv("MANAGED_SECRET_KEY") or os.getenv("APP_SECRET_ENCRYPTION_KEY") or "").strip())


def _build_fernet() -> Fernet:
    seed = os.getenv("MANAGED_SECRET_KEY") or os.getenv("APP_SECRET_ENCRYPTION_KEY") or settings.SECRET_KEY
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


def managed_secret_key_source() -> str:
    if (os.getenv("MANAGED_SECRET_KEY") or "").strip():
        return "MANAGED_SECRET_KEY"
    if (os.getenv("APP_SECRET_ENCRYPTION_KEY") or "").strip():
        return "APP_SECRET_ENCRYPTION_KEY"
    return "SECRET_KEY"


def verify_managed_secret_roundtrip() -> bool:
    probe = {"kind": "managed_secret_probe", "version": 1}
    return _decrypt_payload(_encrypt_payload(probe)) == probe


def list_undecryptable_secrets(limit: int = 500) -> list[str]:
    """Return identifiers of stored secrets the current key cannot decrypt.

    A non-empty result means secrets were written under a different key seed
    (MANAGED_SECRET_KEY / SECRET_KEY changed, or another process wrote them
    with its own key) and every consumer of those secrets will fail at runtime.
    """
    broken: list[str] = []
    for secret in ManagedSecret.objects.all().order_by("namespace", "object_id", "key")[: max(int(limit), 1)]:
        try:
            _decrypt_payload(secret.ciphertext)
        except ManagedSecretError:
            broken.append(f"{secret.namespace}:{secret.object_id}:{secret.key}")
    return broken


def _upsert(
    namespace: str, object_id: int, payload: Any, *, key: str = "default", metadata: dict | None = None
) -> ManagedSecret:
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


def set_studio_pipeline_secrets(pipeline_id: int, nodes: dict[str, dict[str, str]]) -> None:
    """Store all write-only node credentials for one Studio pipeline."""
    clean_nodes: dict[str, dict[str, str]] = {}
    for raw_node_id, raw_values in (nodes or {}).items():
        node_id = str(raw_node_id or "").strip()
        if not node_id or not isinstance(raw_values, dict):
            continue
        values = {
            str(key): str(value) for key, value in raw_values.items() if str(key).strip() and str(value or "").strip()
        }
        if values:
            clean_nodes[node_id] = values

    if not clean_nodes:
        _delete(STUDIO_PIPELINE_SECRETS_NAMESPACE, pipeline_id)
        return
    secret_names = sorted(f"{node_id}:{key}" for node_id, values in clean_nodes.items() for key in values)
    _upsert(
        STUDIO_PIPELINE_SECRETS_NAMESPACE,
        pipeline_id,
        {"nodes": clean_nodes},
        metadata={"kind": "studio_pipeline_node_credentials", "secret_names": secret_names},
    )


def get_studio_pipeline_secrets(pipeline_id: int) -> dict[str, dict[str, str]]:
    payload = _get(STUDIO_PIPELINE_SECRETS_NAMESPACE, pipeline_id, default={})
    raw_nodes = payload.get("nodes") if isinstance(payload, dict) else {}
    if not isinstance(raw_nodes, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for raw_node_id, raw_values in raw_nodes.items():
        node_id = str(raw_node_id or "").strip()
        if not node_id or not isinstance(raw_values, dict):
            continue
        values = {
            str(key): str(value) for key, value in raw_values.items() if str(key).strip() and str(value or "").strip()
        }
        if values:
            result[node_id] = values
    return result


def delete_studio_pipeline_secrets(pipeline_id: int) -> None:
    _delete(STUDIO_PIPELINE_SECRETS_NAMESPACE, pipeline_id)


def set_playbook_binding_secret_values(binding_profile_id: int, values: dict[str, str]) -> None:
    """Store a binding profile's secret variables as one encrypted envelope."""
    clean = {str(key): str(value) for key, value in (values or {}).items() if str(key).strip() and value is not None}
    if not clean:
        _delete(PLAYBOOK_BINDING_VARIABLES_NAMESPACE, binding_profile_id)
        return
    _upsert(
        PLAYBOOK_BINDING_VARIABLES_NAMESPACE,
        binding_profile_id,
        {"values": clean},
        metadata={"kind": "playbook_binding_variables", "variable_names": sorted(clean)},
    )


def get_playbook_binding_secret_values(binding_profile_id: int) -> dict[str, str]:
    payload = _get(PLAYBOOK_BINDING_VARIABLES_NAMESPACE, binding_profile_id, default={})
    values = payload.get("values") if isinstance(payload, dict) else {}
    if not isinstance(values, dict):
        return {}
    return {str(key): str(value) for key, value in values.items()}


def delete_playbook_binding_secret_values(binding_profile_id: int) -> None:
    _delete(PLAYBOOK_BINDING_VARIABLES_NAMESPACE, binding_profile_id)


def set_playbook_run_variables(run_id: int, values: dict[str, Any]) -> None:
    """Persist execution variables encrypted until the worker consumes them."""
    if not values:
        _delete(PLAYBOOK_RUN_VARIABLES_NAMESPACE, run_id)
        return
    _upsert(
        PLAYBOOK_RUN_VARIABLES_NAMESPACE,
        run_id,
        {"values": values},
        metadata={"kind": "playbook_run_variables", "variable_names": sorted(str(key) for key in values)},
    )


def get_playbook_run_variables(run_id: int) -> dict[str, Any]:
    payload = _get(PLAYBOOK_RUN_VARIABLES_NAMESPACE, run_id, default={})
    values = payload.get("values") if isinstance(payload, dict) else {}
    return values if isinstance(values, dict) else {}


def delete_playbook_run_variables(run_id: int) -> None:
    _delete(PLAYBOOK_RUN_VARIABLES_NAMESPACE, run_id)


def set_playbook_run_master_password(run_id: int, master_password: str) -> None:
    """Persist the per-run unlock password outside dispatch/run JSON fields."""
    value = str(master_password or "")
    if not value:
        _delete(PLAYBOOK_RUN_MASTER_PASSWORD_NAMESPACE, run_id)
        return
    _upsert(
        PLAYBOOK_RUN_MASTER_PASSWORD_NAMESPACE,
        run_id,
        {"master_password": value},
        metadata={"kind": "playbook_run_master_password"},
    )


def get_playbook_run_master_password(run_id: int) -> str:
    payload = _get(PLAYBOOK_RUN_MASTER_PASSWORD_NAMESPACE, run_id, default={})
    if isinstance(payload, dict):
        return str(payload.get("master_password") or "")
    return ""


def delete_playbook_run_master_password(run_id: int) -> None:
    _delete(PLAYBOOK_RUN_MASTER_PASSWORD_NAMESPACE, run_id)


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


def set_server_sudo_secret(server_id: int, secret_value: str) -> None:
    value = (secret_value or "").strip()
    if not value:
        _delete(SERVER_SUDO_NAMESPACE, server_id)
        return
    _upsert(
        SERVER_SUDO_NAMESPACE,
        server_id,
        {"secret": value},
        metadata={"kind": "server_sudo"},
    )


def get_server_sudo_secret(server_id: int) -> str:
    payload = _get(SERVER_SUDO_NAMESPACE, server_id, default={})
    if isinstance(payload, dict):
        return str(payload.get("secret") or "")
    return ""


def has_server_sudo_secret(server_id: int) -> bool:
    return _has(SERVER_SUDO_NAMESPACE, server_id)


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


def set_notification_secret(key: str, secret_value: str) -> None:
    secret_key = (key or "").strip()
    value = (secret_value or "").strip()
    if not secret_key:
        raise ManagedSecretError("Notification secret key is required")
    if not value:
        _delete(NOTIFICATION_SECRET_NAMESPACE, NOTIFICATION_SECRET_OBJECT_ID, key=secret_key)
        return
    _upsert(
        NOTIFICATION_SECRET_NAMESPACE,
        NOTIFICATION_SECRET_OBJECT_ID,
        {"secret": value},
        key=secret_key,
        metadata={"kind": "notification_secret", "key": secret_key},
    )


def get_notification_secret(key: str) -> str:
    secret_key = (key or "").strip()
    if not secret_key:
        return ""
    payload = _get(
        NOTIFICATION_SECRET_NAMESPACE,
        NOTIFICATION_SECRET_OBJECT_ID,
        key=secret_key,
        default={},
    )
    if isinstance(payload, dict):
        return str(payload.get("secret") or "")
    return ""


def has_notification_secret(key: str) -> bool:
    secret_key = (key or "").strip()
    if not secret_key:
        return False
    return _has(NOTIFICATION_SECRET_NAMESPACE, NOTIFICATION_SECRET_OBJECT_ID, key=secret_key)


def _normalize_llm_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    if value == "anthropic":
        value = "claude"
    if value not in LLM_API_KEY_PROVIDERS:
        raise ManagedSecretError(f"Unsupported LLM API key provider: {provider}")
    return value


def set_llm_api_key(provider: str, api_key: str) -> None:
    provider_key = _normalize_llm_provider(provider)
    value = (api_key or "").strip()
    if not value:
        _delete(LLM_API_KEY_NAMESPACE, LLM_API_KEY_OBJECT_ID, key=provider_key)
        return
    _upsert(
        LLM_API_KEY_NAMESPACE,
        LLM_API_KEY_OBJECT_ID,
        {"api_key": value},
        key=provider_key,
        metadata={
            "kind": "llm_api_key",
            "provider": provider_key,
            "env_name": LLM_API_KEY_PROVIDERS[provider_key],
        },
    )


def delete_llm_api_key(provider: str) -> None:
    provider_key = _normalize_llm_provider(provider)
    _delete(LLM_API_KEY_NAMESPACE, LLM_API_KEY_OBJECT_ID, key=provider_key)


def get_llm_api_key(provider: str) -> str:
    provider_key = _normalize_llm_provider(provider)
    payload = _get(LLM_API_KEY_NAMESPACE, LLM_API_KEY_OBJECT_ID, key=provider_key, default={})
    if isinstance(payload, dict):
        return str(payload.get("api_key") or "")
    return ""


def has_llm_api_key(provider: str) -> bool:
    provider_key = _normalize_llm_provider(provider)
    return _has(LLM_API_KEY_NAMESPACE, LLM_API_KEY_OBJECT_ID, key=provider_key)


def set_kubernetes_provider_token(provider_id: int, token: str) -> None:
    value = (token or "").strip()
    if not value:
        _delete(KUBERNETES_PROVIDER_TOKEN_NAMESPACE, provider_id)
        return
    _upsert(
        KUBERNETES_PROVIDER_TOKEN_NAMESPACE,
        provider_id,
        {"token": value},
        metadata={"kind": "kubernetes_provider_token"},
    )


def get_kubernetes_provider_token(provider_id: int) -> str:
    payload = _get(KUBERNETES_PROVIDER_TOKEN_NAMESPACE, provider_id, default={})
    if isinstance(payload, dict):
        return str(payload.get("token") or "")
    return ""


def has_kubernetes_provider_token(provider_id: int) -> bool:
    return _has(KUBERNETES_PROVIDER_TOKEN_NAMESPACE, provider_id)


def delete_kubernetes_provider_token(provider_id: int) -> None:
    _delete(KUBERNETES_PROVIDER_TOKEN_NAMESPACE, provider_id)
