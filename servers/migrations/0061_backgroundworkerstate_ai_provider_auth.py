from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("servers", "0060_agentrun_provider_execution_mode")]

    operations = [
        migrations.AlterField(
            model_name="backgroundworkerstate",
            name="worker_kind",
            field=models.CharField(
                choices=[
                    ("memory_dreams", "Memory Dreams"),
                    ("agent_execution", "Agent Execution"),
                    ("scheduled_agents", "Scheduled Agents"),
                    ("watchers", "Watchers"),
                    ("ai_provider_auth", "AI Provider Authentication"),
                ],
                max_length=40,
            ),
        )
    ]
