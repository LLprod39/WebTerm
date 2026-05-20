"""Tests for automatic OS detection scheduling helpers."""

from datetime import timedelta

import pytest
from django.utils import timezone

from servers.models import Server
from servers.os_detect_service import os_detect_cooldown_allows, server_needs_os_detect


@pytest.mark.django_db
def test_server_needs_os_detect_when_empty(django_user_model):
    user = django_user_model.objects.create_user(username="osuser", password="x")
    server = Server.objects.create(
        user=user,
        name="srv",
        host="10.0.0.1",
        port=22,
        username="root",
        server_type="ssh",
    )
    assert server_needs_os_detect(server) is True


@pytest.mark.django_db
def test_os_detect_cooldown_blocks_recent_failure(django_user_model):
    user = django_user_model.objects.create_user(username="osuser2", password="x")
    server = Server.objects.create(
        user=user,
        name="srv2",
        host="10.0.0.2",
        port=22,
        username="root",
        server_type="ssh",
        detected_os_attempted_at=timezone.now(),
    )
    assert os_detect_cooldown_allows(server) is False
    assert os_detect_cooldown_allows(server, force=True) is True


@pytest.mark.django_db
def test_os_detect_cooldown_allows_stale_success(django_user_model):
    user = django_user_model.objects.create_user(username="osuser3", password="x")
    old = timezone.now() - timedelta(days=10)
    server = Server.objects.create(
        user=user,
        name="srv3",
        host="10.0.0.3",
        port=22,
        username="root",
        server_type="ssh",
        detected_os="ubuntu",
        detected_os_meta={"detected_at": old.isoformat()},
        detected_os_attempted_at=old,
    )
    assert server_needs_os_detect(server) is True
    assert os_detect_cooldown_allows(server) is True
