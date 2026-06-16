from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0032_serveragent_runtime_inputs"),
    ]

    operations = [
        migrations.AddField(
            model_name="serveragent",
            name="sudo_policy",
            field=models.CharField(
                choices=[
                    ("disabled", "Disabled"),
                    ("ask", "Ask when needed"),
                    ("approved", "Approved for this run"),
                ],
                default="disabled",
                help_text="Controlled sudo policy for SSH commands executed by this agent.",
                max_length=20,
            ),
        ),
    ]
