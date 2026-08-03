from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User

from app.shell_commands import is_read_only_command
from servers.agents.agent_templates import AGENT_TEMPLATES
from servers.models import ServerAgent


def test_service_health_template_is_compatible_with_read_only_servers() -> None:
    commands = AGENT_TEMPLATES["service_health"]["commands"]

    assert commands
    assert all(is_read_only_command(command) for command in commands)


@pytest.mark.django_db
def test_service_health_migration_updates_only_unchanged_legacy_agents() -> None:
    migration = import_module("servers.migrations.0057_update_service_health_read_only_commands")
    user = User.objects.create_user(username="service-health-template-owner", password="x")
    legacy_commands = list(migration.LEGACY_COMMANDS)
    custom_commands = [*legacy_commands[:-1], "uptime"]
    default_agent = ServerAgent.objects.create(
        user=user,
        name="Default service health",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_SERVICE,
        commands=legacy_commands,
    )
    custom_agent = ServerAgent.objects.create(
        user=user,
        name="Customized service health",
        mode=ServerAgent.MODE_MINI,
        agent_type=ServerAgent.TYPE_SERVICE,
        commands=custom_commands,
    )

    migration.update_service_health_commands(django_apps, None)

    default_agent.refresh_from_db()
    custom_agent.refresh_from_db()
    assert default_agent.commands == AGENT_TEMPLATES["service_health"]["commands"]
    assert custom_agent.commands == custom_commands
