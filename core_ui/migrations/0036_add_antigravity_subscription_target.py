# Generated manually for Gemini Antigravity subscription target.

from django.db import migrations, models

import app.ai_runtime.targets


class Migration(migrations.Migration):

    dependencies = [
        ("core_ui", "0035_aiproviderconnectiongrant_max_slots"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiproviderconnection",
            name="target_id",
            field=models.CharField(
                choices=[
                    ("codex_subscription", "Codex subscription"),
                    ("grok_subscription", "Grok subscription"),
                    ("cursor_subscription", "Cursor subscription"),
                    ("antigravity_subscription", "Antigravity subscription"),
                ],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="aiproviderpool",
            name="target_id",
            field=models.CharField(
                choices=[
                    ("codex_subscription", "Codex subscription"),
                    ("grok_subscription", "Grok subscription"),
                    ("cursor_subscription", "Cursor subscription"),
                    ("antigravity_subscription", "Antigravity subscription"),
                ],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="aiproviderpreference",
            name="target_id",
            field=models.CharField(
                choices=[(target.value, target.value) for target in app.ai_runtime.targets.ProviderTarget],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="aiproviderinvocation",
            name="target_id",
            field=models.CharField(
                choices=[(target.value, target.value) for target in app.ai_runtime.targets.ProviderTarget],
                max_length=64,
            ),
        ),
    ]
