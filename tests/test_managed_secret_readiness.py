"""Tests for managed-secret key consistency detection.

Covers the incident class where secrets were encrypted by a process with one
MANAGED_SECRET_KEY/SECRET_KEY seed and read by a process with another
("Managed secret cannot be decrypted with the current server key").
"""

import base64
import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from core_ui.managed_secrets import (
    get_server_auth_secret,
    list_undecryptable_secrets,
    set_server_auth_secret,
    verify_managed_secret_roundtrip,
)
from core_ui.models import ManagedSecret
from web_ui.services.settings_readiness_config import managed_secret_check

pytestmark = pytest.mark.django_db


def _encrypt_with_seed(seed: str, payload: dict) -> str:
    digest = hashlib.sha256(f"{seed}:managed-secret:v1".encode()).digest()
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(digest)).encrypt(raw).decode("utf-8")


def test_roundtrip_and_own_secrets_decryptable():
    assert verify_managed_secret_roundtrip() is True
    set_server_auth_secret(101, "s3cret-password")
    assert get_server_auth_secret(101) == "s3cret-password"
    assert list_undecryptable_secrets() == []


def test_secret_written_under_foreign_key_is_reported():
    ManagedSecret.objects.create(
        namespace="server_auth_secret",
        object_id=202,
        key="default",
        ciphertext=_encrypt_with_seed("some-other-process-key", {"secret": "x"}),
        metadata={"kind": "server_auth"},
    )
    assert list_undecryptable_secrets() == ["server_auth_secret:202:default"]


def test_readiness_check_flags_undecryptable_secrets():
    ManagedSecret.objects.create(
        namespace="server_auth_secret",
        object_id=303,
        key="default",
        ciphertext=_encrypt_with_seed("stale-rotated-key", {"secret": "x"}),
        metadata={"kind": "server_auth"},
    )
    result = managed_secret_check()
    assert result["status"] == "error"
    assert result["details"]["undecryptable_count"] == 1
    assert "server_auth_secret:303:default" in result["details"]["undecryptable"]


def test_readiness_check_healthy_without_broken_secrets(monkeypatch):
    monkeypatch.setenv("MANAGED_SECRET_KEY", "dedicated-managed-secret-key-for-tests-0123456789")
    set_server_auth_secret(404, "ok-password")
    result = managed_secret_check()
    assert result["status"] == "ready"
    assert "undecryptable" not in (result.get("details") or {})
