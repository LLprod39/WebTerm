from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("studio", "0011_mcpserverpool_headers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agentconfig",
            name="skill_slugs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of attached skill slugs, e.g. ["kubernetes-safety"]',
            ),
        ),
    ]
