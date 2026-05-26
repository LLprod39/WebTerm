from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from servers.models import Server, ServerShare
from servers.services.terminal_access import (
    get_terminal_server_sync,
    get_terminal_session_limit_sync,
    resolve_server_secret_sync,
)


def _make_server(user: User, *, auth_method: str = "password") -> Server:
    return Server.objects.create(
        user=user,
        name="terminal-access-srv",
        host="10.0.0.60",
        username="root",
        auth_method=auth_method,
    )


@pytest.mark.django_db
def test_get_terminal_server_sync_allows_owner():
    user = User.objects.create_user(username="terminal-owner", password="x")
    server = _make_server(user)

    assert get_terminal_server_sync(user_id=user.id, server_id=server.id) == server


@pytest.mark.django_db
def test_get_terminal_server_sync_allows_active_share():
    owner = User.objects.create_user(username="terminal-share-owner", password="x")
    shared_user = User.objects.create_user(username="terminal-share-user", password="x")
    server = _make_server(owner)
    ServerShare.objects.create(
        server=server,
        user=shared_user,
        shared_by=owner,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    assert get_terminal_server_sync(user_id=shared_user.id, server_id=server.id) == server


@pytest.mark.django_db
def test_get_terminal_server_sync_rejects_revoked_share():
    owner = User.objects.create_user(username="terminal-revoke-owner", password="x")
    shared_user = User.objects.create_user(username="terminal-revoke-user", password="x")
    server = _make_server(owner)
    ServerShare.objects.create(
        server=server,
        user=shared_user,
        shared_by=owner,
        is_revoked=True,
    )

    with pytest.raises(ObjectDoesNotExist):
        get_terminal_server_sync(user_id=shared_user.id, server_id=server.id)


@pytest.mark.django_db
def test_resolve_server_secret_sync_uses_plain_fallback_for_password_auth():
    user = User.objects.create_user(username="terminal-secret", password="x")
    server = _make_server(user)

    assert (
        resolve_server_secret_sync(
            server_id=server.id,
            master_password="",
            plain_password="plain-pass",
        )
        == "plain-pass"
    )


@pytest.mark.django_db
def test_resolve_server_secret_sync_returns_empty_for_plain_key_auth():
    user = User.objects.create_user(username="terminal-key", password="x")
    server = _make_server(user, auth_method="key")

    assert (
        resolve_server_secret_sync(
            server_id=server.id,
            master_password="",
            plain_password="ignored",
        )
        == ""
    )


@pytest.mark.django_db
def test_get_terminal_session_limit_sync_handles_existing_user():
    user = User.objects.create_user(username="terminal-limit", password="x")

    result = get_terminal_session_limit_sync(user.id)

    assert result is None or "error" in result
