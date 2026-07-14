"""Tests for optional legacy agent budget bump command."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from servers.agent_budgets import FULL_DEFAULT_MAX_ITERATIONS, FULL_DEFAULT_SESSION_TIMEOUT_SEC
from servers.models import ServerAgent


@pytest.mark.django_db
def test_bump_agent_budget_defaults_dry_run_and_apply(capsys):
    user = User.objects.create_user(username="budget-bump", password="x")
    legacy = ServerAgent.objects.create(
        user=user,
        name="legacy",
        mode=ServerAgent.MODE_FULL,
        max_iterations=20,
        session_timeout_seconds=600,
    )
    modern = ServerAgent.objects.create(
        user=user,
        name="modern",
        mode=ServerAgent.MODE_FULL,
        max_iterations=FULL_DEFAULT_MAX_ITERATIONS,
        session_timeout_seconds=FULL_DEFAULT_SESSION_TIMEOUT_SEC,
    )

    call_command("bump_agent_budget_defaults")
    legacy.refresh_from_db()
    assert legacy.max_iterations == 20
    assert legacy.session_timeout_seconds == 600

    call_command("bump_agent_budget_defaults", "--apply")
    legacy.refresh_from_db()
    modern.refresh_from_db()
    assert legacy.max_iterations == FULL_DEFAULT_MAX_ITERATIONS
    assert legacy.session_timeout_seconds == FULL_DEFAULT_SESSION_TIMEOUT_SEC
    assert modern.max_iterations == FULL_DEFAULT_MAX_ITERATIONS
