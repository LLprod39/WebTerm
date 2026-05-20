from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0028_server_detected_os"),
    ]

    operations = [
        migrations.AddField(
            model_name="server",
            name="detected_os_attempted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Last automatic or manual OS detection attempt (cooldown for retries)",
                null=True,
            ),
        ),
    ]
