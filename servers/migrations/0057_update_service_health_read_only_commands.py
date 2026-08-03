from django.db import migrations


LEGACY_COMMANDS = [
    "systemctl list-units --type=service --state=running --no-pager --plain 2>/dev/null | head -30",
    "systemctl list-units --type=service --state=failed --no-pager --plain 2>/dev/null || true",
    "systemctl list-units --type=service --state=inactive --no-pager --plain 2>/dev/null | head -15 || true",
    "journalctl -b --no-pager -q -p 3 2>/dev/null | grep -i 'service' | tail -15 || true",
]

READ_ONLY_COMMANDS = [
    "systemctl list-units --type=service --state=running --no-pager --plain | head -30",
    "systemctl list-units --type=service --state=failed --no-pager --plain || true",
    "systemctl list-units --type=service --state=inactive --no-pager --plain | head -15 || true",
    "journalctl -b --no-pager -q -p 3 | grep -i 'service' | tail -15 || true",
]


def update_service_health_commands(apps, _schema_editor):
    ServerAgent = apps.get_model("servers", "ServerAgent")
    ServerAgent.objects.filter(
        agent_type="service_health",
        commands=LEGACY_COMMANDS,
    ).update(commands=READ_ONLY_COMMANDS)


def restore_service_health_commands(apps, _schema_editor):
    ServerAgent = apps.get_model("servers", "ServerAgent")
    ServerAgent.objects.filter(
        agent_type="service_health",
        commands=READ_ONLY_COMMANDS,
    ).update(commands=LEGACY_COMMANDS)


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0056_commandsnapshot_srv_snapshot_created_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(update_service_health_commands, restore_service_health_commands),
    ]
