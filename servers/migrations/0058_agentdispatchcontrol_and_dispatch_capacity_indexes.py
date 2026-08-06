from django.db import migrations, models


def create_control_rows(apps, schema_editor):
    control = apps.get_model("servers", "AgentDispatchControl")
    control.objects.get_or_create(name="claim-capacity")
    control.objects.get_or_create(name="launch-admission")


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0057_update_service_health_read_only_commands"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentDispatchControl",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=32, unique=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="agentrundispatch",
            index=models.Index(fields=["status", "lease_expires_at"], name="agent_dispatch_lease_idx"),
        ),
        migrations.AddIndex(
            model_name="agentrundispatch",
            index=models.Index(fields=["user", "status", "queued_at"], name="agent_dispatch_user_queue_idx"),
        ),
        migrations.RunPython(create_control_rows, migrations.RunPython.noop),
    ]
