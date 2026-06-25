from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0034_server_sudo_auth"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentrun",
            name="report_payload",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Canonical structured report payload rendered by the agent run UI.",
            ),
        ),
    ]
