from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from app.runtime_limits import get_active_terminal_connections_queryset, get_terminal_session_limit_error
from core_ui.models import UserAppPermission
from servers.models import Server, ServerConnection


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _create_server(user: User, *, name: str = "Runtime Limit Server") -> Server:
    return Server.objects.create(
        user=user,
        name=name,
        host=f"{name.lower().replace(' ', '-')}.example.internal",
        port=22,
        username="root",
        auth_method="password",
        server_type="ssh",
    )


@pytest.mark.django_db
def test_terminal_limit_ignores_stale_connected_rows(settings):
    settings.SSH_TERMINAL_SESSIONS_PER_USER_LIMIT = 1
    settings.SSH_TERMINAL_SESSIONS_GLOBAL_LIMIT = 0
    settings.SSH_TERMINAL_SESSION_STALE_SECONDS = 180

    user = User.objects.create_user(username="stale-limit-user", password="x")
    server = _create_server(user)
    connection = ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-stale-limit",
        status="connected",
    )
    stale_at = timezone.now() - timedelta(minutes=10)
    ServerConnection.objects.filter(pk=connection.pk).update(
        connected_at=stale_at,
        last_seen_at=stale_at,
    )

    assert get_terminal_session_limit_error(user) is None

    connection.refresh_from_db()
    assert connection.status == "disconnected"
    assert connection.disconnected_at is not None


@pytest.mark.django_db
def test_active_terminal_queryset_excludes_stale_and_disconnected_rows(settings):
    settings.SSH_TERMINAL_SESSION_STALE_SECONDS = 180

    user = User.objects.create_user(username="active-terminal-user", password="x")
    server = _create_server(user, name="Active Filter Server")

    fresh = ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-fresh",
        status="connected",
    )
    stale = ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-stale",
        status="connected",
    )
    disconnected = ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-disconnected",
        status="disconnected",
    )

    stale_at = timezone.now() - timedelta(minutes=12)
    ServerConnection.objects.filter(pk=stale.pk).update(last_seen_at=stale_at, connected_at=stale_at)
    ServerConnection.objects.filter(pk=disconnected.pk).update(disconnected_at=timezone.now())

    active_ids = set(get_active_terminal_connections_queryset().values_list("connection_id", flat=True))

    assert fresh.connection_id in active_ids
    assert stale.connection_id not in active_ids
    assert disconnected.connection_id not in active_ids


@pytest.mark.django_db
def test_frontend_bootstrap_ignores_stale_terminal_online_status(client, settings):
    settings.SSH_TERMINAL_SESSION_STALE_SECONDS = 180

    user = User.objects.create_user(username="bootstrap-terminal-user", password="x")
    _grant_feature(user, "servers")
    server = _create_server(user, name="Bootstrap Server")
    server.last_connected = timezone.now() - timedelta(hours=2)
    server.save(update_fields=["last_connected"])

    connection = ServerConnection.objects.create(
        server=server,
        user=user,
        connection_id="term-bootstrap-stale",
        status="connected",
    )
    stale_at = timezone.now() - timedelta(minutes=9)
    ServerConnection.objects.filter(pk=connection.pk).update(
        connected_at=stale_at,
        last_seen_at=stale_at,
    )

    client.force_login(user)
    response = client.get("/servers/api/frontend/bootstrap/")

    assert response.status_code == 200
    payload = response.json()
    item = next(entry for entry in payload["servers"] if entry["id"] == server.id)
    assert item["status"] == "offline"
