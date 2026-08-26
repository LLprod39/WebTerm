from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0066_server_ai_read_only_release_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="execution_outcome",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Durable kernel outcome facts for the run: outcome, reason, exit_reason, "
                    "verification summary and task/tool counters."
                ),
            ),
        ),
    ]
