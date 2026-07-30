"""Tests for managed-secret key consistency detection.

Covers the incident class where secrets were encrypted by a process with one
MANAGED_SECRET_KEY/SECRET_KEY seed and read by a process with another
("Managed secret cannot be decrypted with the current server key").
"""

import base64
import hashlib
import io
import json

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command

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


def test_new_managed_secrets_use_authenticated_v2_key_id(monkeypatch):
    monkeypatch.setenv("MANAGED_SECRET_KEY", "current-managed-secret-key-for-v2-tests")
    monkeypatch.setenv("MANAGED_SECRET_KEY_ID", "current-2026-07")
    monkeypatch.delenv("MANAGED_SECRET_PREVIOUS_KEYS", raising=False)

    set_server_auth_secret(501, "v2-password")

    secret = ManagedSecret.objects.get(namespace="server_auth_secret", object_id=501)
    assert secret.ciphertext.startswith("v2:current-2026-07:")
    assert get_server_auth_secret(501) == "v2-password"


def test_rotate_managed_secrets_keeps_old_and_new_keys_readable_without_downtime(monkeypatch):
    old_key = "old-managed-secret-key-for-rotation-tests"
    new_key = "new-managed-secret-key-for-rotation-tests"
    monkeypatch.setenv("MANAGED_SECRET_KEY", old_key)
    monkeypatch.setenv("MANAGED_SECRET_KEY_ID", "old-2026-06")
    monkeypatch.delenv("MANAGED_SECRET_PREVIOUS_KEYS", raising=False)
    set_server_auth_secret(601, "rotation-password")

    secret = ManagedSecret.objects.get(namespace="server_auth_secret", object_id=601)
    assert secret.ciphertext.startswith("v2:old-2026-06:")

    monkeypatch.setenv("MANAGED_SECRET_KEY", new_key)
    monkeypatch.setenv("MANAGED_SECRET_KEY_ID", "new-2026-07")
    monkeypatch.setenv("MANAGED_SECRET_PREVIOUS_KEYS", json.dumps({"old-2026-06": old_key}))
    assert get_server_auth_secret(601) == "rotation-password"

    stdout = io.StringIO()
    call_command(
        "rotate_managed_secrets",
        expect_key_id="new-2026-07",
        batch_size=1,
        stdout=stdout,
    )

    secret.refresh_from_db()
    assert secret.ciphertext.startswith("v2:new-2026-07:")
    assert secret.metadata["encryption"] == {"version": 2, "key_id": "new-2026-07"}
    assert "rotated=1" in stdout.getvalue()

    monkeypatch.delenv("MANAGED_SECRET_PREVIOUS_KEYS")
    assert get_server_auth_secret(601) == "rotation-password"
    assert list_undecryptable_secrets(limit=None) == []


def test_rotate_managed_secrets_migrates_legacy_v1_ciphertext(monkeypatch):
    old_key = "legacy-managed-secret-key-for-rotation-tests"
    monkeypatch.setenv("MANAGED_SECRET_KEY", "new-managed-secret-key-for-legacy-migration")
    monkeypatch.setenv("MANAGED_SECRET_KEY_ID", "new-legacy-migration")
    monkeypatch.setenv("MANAGED_SECRET_PREVIOUS_KEYS", json.dumps({"legacy-v1": old_key}))
    ManagedSecret.objects.create(
        namespace="server_auth_secret",
        object_id=701,
        key="default",
        ciphertext=_encrypt_with_seed(old_key, {"secret": "legacy-password"}),
        metadata={"kind": "server_auth"},
    )

    call_command("rotate_managed_secrets", expect_key_id="new-legacy-migration", stdout=io.StringIO())

    secret = ManagedSecret.objects.get(namespace="server_auth_secret", object_id=701)
    assert secret.ciphertext.startswith("v2:new-legacy-migration:")
    monkeypatch.delenv("MANAGED_SECRET_PREVIOUS_KEYS")
    assert get_server_auth_secret(701) == "legacy-password"
