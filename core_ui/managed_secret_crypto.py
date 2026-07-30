"""Versioned encryption and keyring handling for managed secret envelopes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

V2_PREFIX = "v2"
PREVIOUS_KEYS_ENV = "MANAGED_SECRET_PREVIOUS_KEYS"
CURRENT_KEY_ID_ENV = "MANAGED_SECRET_KEY_ID"
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_V2_HKDF_SALT = b"webterm-managed-secrets-v2"
_V2_HKDF_INFO = b"fernet-envelope-key"


class ManagedSecretError(RuntimeError):
    pass


@dataclass(frozen=True)
class ManagedSecretKeyring:
    current_key_id: str
    current_fernet: Fernet
    fernet_by_id: dict[str, Fernet]
    multi_fernet: MultiFernet
    legacy_multi_fernet: MultiFernet


def allow_secret_key_fallback() -> bool:
    return (os.getenv("ALLOW_SECRET_KEY_MANAGED_ENCRYPTION", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def uses_dedicated_managed_secret_key() -> bool:
    return bool((os.getenv("MANAGED_SECRET_KEY") or os.getenv("APP_SECRET_ENCRYPTION_KEY") or "").strip())


def managed_secret_key_source() -> str:
    if (os.getenv("MANAGED_SECRET_KEY") or "").strip():
        return "MANAGED_SECRET_KEY"
    if (os.getenv("APP_SECRET_ENCRYPTION_KEY") or "").strip():
        return "APP_SECRET_ENCRYPTION_KEY"
    return "SECRET_KEY"


def _current_seed() -> str:
    return str(
        os.getenv("MANAGED_SECRET_KEY")
        or os.getenv("APP_SECRET_ENCRYPTION_KEY")
        or settings.SECRET_KEY
    )


def _derived_key_id(seed: str) -> str:
    digest = hashlib.sha256(f"{seed}:managed-secret:key-id:v2".encode("utf-8")).hexdigest()
    return digest[:16]


def _validate_key_id(value: str, *, source: str) -> str:
    key_id = str(value or "").strip()
    if not _KEY_ID_RE.fullmatch(key_id):
        raise ManagedSecretError(f"{source} must contain 1-64 letters, numbers, dots, underscores, or dashes")
    return key_id


def managed_secret_current_key_id() -> str:
    seed = _current_seed()
    configured = str(os.getenv(CURRENT_KEY_ID_ENV, "") or "").strip()
    return _validate_key_id(configured, source=CURRENT_KEY_ID_ENV) if configured else _derived_key_id(seed)


def _parse_previous_keys() -> list[tuple[str, str]]:
    raw = str(os.getenv(PREVIOUS_KEYS_ENV, "") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManagedSecretError(f"{PREVIOUS_KEYS_ENV} must be a JSON object mapping key ids to keys") from exc
    if not isinstance(parsed, dict):
        raise ManagedSecretError(f"{PREVIOUS_KEYS_ENV} must be a JSON object mapping key ids to keys")

    result: list[tuple[str, str]] = []
    for raw_key_id, raw_seed in parsed.items():
        key_id = _validate_key_id(str(raw_key_id), source=PREVIOUS_KEYS_ENV)
        seed = str(raw_seed or "")
        if not seed.strip():
            raise ManagedSecretError(f"{PREVIOUS_KEYS_ENV} contains an empty key for {key_id}")
        result.append((key_id, seed))
    return result


def _legacy_fernet(seed: str) -> Fernet:
    digest = hashlib.sha256(f"{seed}:managed-secret:v1".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _v2_fernet(seed: str) -> Fernet:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_V2_HKDF_SALT,
        info=_V2_HKDF_INFO,
    ).derive(seed.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def build_managed_secret_keyring() -> ManagedSecretKeyring:
    current_seed = _current_seed()
    current_key_id = managed_secret_current_key_id()
    entries = [(current_key_id, current_seed), *_parse_previous_keys()]
    fernet_by_id: dict[str, Fernet] = {}
    seeds_by_id: dict[str, str] = {}
    ordered_v2: list[Fernet] = []
    ordered_legacy: list[Fernet] = []

    for key_id, seed in entries:
        if key_id in seeds_by_id and not secrets.compare_digest(seeds_by_id[key_id], seed):
            raise ManagedSecretError(f"Managed secret key id {key_id} is configured with multiple keys")
        if key_id in fernet_by_id:
            continue
        seeds_by_id[key_id] = seed
        fernet = _v2_fernet(seed)
        fernet_by_id[key_id] = fernet
        ordered_v2.append(fernet)
        ordered_legacy.append(_legacy_fernet(seed))

    return ManagedSecretKeyring(
        current_key_id=current_key_id,
        current_fernet=fernet_by_id[current_key_id],
        fernet_by_id=fernet_by_id,
        multi_fernet=MultiFernet(ordered_v2),
        legacy_multi_fernet=MultiFernet(ordered_legacy),
    )


def managed_secret_ciphertext_key_id(ciphertext: str) -> str | None:
    raw = str(ciphertext or "")
    if not raw.startswith(f"{V2_PREFIX}:"):
        return None
    parts = raw.split(":", 2)
    if len(parts) != 3 or not _KEY_ID_RE.fullmatch(parts[1]):
        raise ManagedSecretError("Managed secret v2 envelope header is corrupted")
    return parts[1]


def encrypt_managed_payload(payload: Any) -> str:
    keyring = build_managed_secret_keyring()
    envelope = {"key_id": keyring.current_key_id, "payload": payload}
    raw = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = keyring.current_fernet.encrypt(raw).decode("utf-8")
    return f"{V2_PREFIX}:{keyring.current_key_id}:{token}"


def decrypt_managed_payload(ciphertext: str) -> Any:
    keyring = build_managed_secret_keyring()
    raw_ciphertext = str(ciphertext or "")
    key_id = managed_secret_ciphertext_key_id(raw_ciphertext)
    try:
        if key_id is None:
            raw = keyring.legacy_multi_fernet.decrypt(raw_ciphertext.encode("utf-8"))
            return json.loads(raw.decode("utf-8"))
        if key_id not in keyring.fernet_by_id:
            raise ManagedSecretError(f"Managed secret requires unavailable key id {key_id}")
        token = raw_ciphertext.split(":", 2)[2]
        raw = keyring.multi_fernet.decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ManagedSecretError("Managed secret cannot be decrypted with the configured keyring") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagedSecretError("Managed secret payload is corrupted") from exc

    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagedSecretError("Managed secret payload is corrupted") from exc
    if not isinstance(envelope, dict) or not secrets.compare_digest(str(envelope.get("key_id") or ""), key_id):
        raise ManagedSecretError("Managed secret v2 envelope key id is corrupted")
    if "payload" not in envelope:
        raise ManagedSecretError("Managed secret v2 envelope payload is missing")
    return envelope["payload"]


def reencrypt_managed_secret(ciphertext: str) -> str:
    return encrypt_managed_payload(decrypt_managed_payload(ciphertext))


def verify_managed_secret_roundtrip() -> bool:
    probe = {"kind": "managed_secret_probe", "version": 2}
    return decrypt_managed_payload(encrypt_managed_payload(probe)) == probe
