from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0033_serveragent_sudo_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="server",
            name="sudo_auth_mode",
            field=models.CharField(
                choices=[
                    ("none", "No sudo auth"),
                    ("nopasswd", "NOPASSWD sudo"),
                    ("stored_password", "Stored sudo password"),
                ],
                default="none",
                help_text="How backend may satisfy sudo prompts for this server.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="server",
            name="encrypted_sudo_password",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="server",
            name="sudo_salt",
            field=models.BinaryField(blank=True, null=True),
        ),
    ]
