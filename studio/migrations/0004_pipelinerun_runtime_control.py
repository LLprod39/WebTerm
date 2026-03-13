from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0003_agentconfig_skill_slugs"),
    ]

    operations = [
        migrations.AddField(
            model_name="pipelinerun",
            name="runtime_control",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Runtime control mailbox for cross-process pipeline control: {stop_requested}",
            ),
        ),
    ]
