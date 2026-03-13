from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0016_agentrun_runtime_control"),
    ]

    operations = [
        migrations.AddField(
            model_name="server",
            name="trusted_host_keys",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Доверенные SSH host keys для strict host verification (TOFU).",
            ),
        ),
    ]
