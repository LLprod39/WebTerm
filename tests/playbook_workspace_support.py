"""Shared fixtures and helpers for playbook workspace API tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def workspace_users(db):
    from django.contrib.auth.models import User

    owner = User.objects.create_user(username="workspace-owner", password="x")
    teammate = User.objects.create_user(username="workspace-teammate", password="x")
    return owner, teammate


def playbook_client(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client


def create_runbook(owner, *, visibility=None):
    from servers.models import Playbook

    if visibility is None:
        visibility = Playbook.VISIBILITY_PRIVATE
    return Playbook.objects.create(
        user=owner,
        name="Revisioned runbook",
        kind=Playbook.KIND_RUNBOOK,
        category=Playbook.CATEGORY_MAINTENANCE,
        visibility=visibility,
        tasks=[{"id": "one", "command": "uptime", "description": "", "continue_on_error": False}],
    )
