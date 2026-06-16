from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("studio", "0009_pipeline_draft_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentconfig",
            name="sudo_policy",
            field=models.CharField(
                choices=[
                    ("disabled", "Disabled"),
                    ("ask", "Ask when needed"),
                    ("approved", "Approved for this run"),
                ],
                default="disabled",
                help_text="Controlled sudo policy for SSH tools used by this agent.",
                max_length=20,
            ),
        ),
    ]
