"""Tests for automatic OS detection scheduling helpers."""

from datetime import timedelta

import pytest
from django.utils import timezone

from servers.models import Server
from servers.os_detect_service import (
    is_known_detected_os,
    os_detect_cooldown_allows,
    server_needs_os_detect,
)


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
    assert is_known_detected_os(server) is False


@pytest.mark.django_db
def test_server_needs_os_detect_when_unknown(django_user_model):
    user = django_user_model.objects.create_user(username="osuser-unk", password="x")
    server = Server.objects.create(
        user=user,
        name="srv-unk",
        host="10.0.0.9",
        port=22,
        username="root",
        server_type="ssh",
        detected_os="unknown",
        detected_os_meta={"unresolved": True, "detected_at": timezone.now().isoformat()},
        detected_os_attempted_at=timezone.now() - timedelta(minutes=20),
    )
    assert is_known_detected_os(server) is False
    assert server_needs_os_detect(server) is True
    assert os_detect_cooldown_allows(server) is True


@pytest.mark.django_db
def test_os_detect_cooldown_blocks_recent_unknown(django_user_model):
    user = django_user_model.objects.create_user(username="osuser2", password="x")
    server = Server.objects.create(
        user=user,
        name="srv2",
        host="10.0.0.2",
        port=22,
        username="root",
        server_type="ssh",
        detected_os="unknown",
        detected_os_attempted_at=timezone.now(),
    )
    assert server_needs_os_detect(server) is True
    assert os_detect_cooldown_allows(server) is False
    assert os_detect_cooldown_allows(server, force=True) is True


@pytest.mark.django_db
def test_os_detect_cooldown_blocks_recent_empty_failure(django_user_model):
    user = django_user_model.objects.create_user(username="osuser-fail", password="x")
    server = Server.objects.create(
        user=user,
        name="srv-fail",
        host="10.0.0.8",
        port=22,
        username="root",
        server_type="ssh",
        detected_os="",
        detected_os_attempted_at=timezone.now(),
    )
    assert os_detect_cooldown_allows(server) is False
    assert os_detect_cooldown_allows(server, force=True) is True


@pytest.mark.django_db
def test_known_os_not_redone_until_stale(django_user_model):
    user = django_user_model.objects.create_user(username="osuser-ok", password="x")
    server = Server.objects.create(
        user=user,
        name="srv-ok",
        host="10.0.0.7",
        port=22,
        username="root",
        server_type="ssh",
        detected_os="ubuntu",
        detected_os_meta={"detected_at": timezone.now().isoformat()},
        detected_os_attempted_at=timezone.now(),
    )
    assert is_known_detected_os(server) is True
    assert server_needs_os_detect(server) is False
    assert os_detect_cooldown_allows(server) is False


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
