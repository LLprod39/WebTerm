from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0031_remove_servermemorypolicy_rdp_semantic_capture_enabled_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="serveragent",
            name="input_artifacts",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Operator-provided documents, task lists and scripts available to the agent",
            ),
        ),
        migrations.AddField(
            model_name="serveragent",
            name="report_delivery",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Report delivery settings, for example Telegram delivery",
            ),
        ),
        migrations.AddField(
            model_name="serveragent",
            name="schedule_config",
            field=models.JSONField(blank=True, default=dict, help_text="Flexible schedule configuration"),
        ),
        migrations.AddField(
            model_name="serveragent",
            name="skill_slugs",
            field=models.JSONField(blank=True, default=list, help_text="Studio skills attached to this agent"),
        ),
    ]
