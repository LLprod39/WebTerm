# Generated manually for ChatSession.KIND_TELEGRAM

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_ui", "0033_telegram_features"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatsession",
            name="kind",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("duty", "Duty"),
                    ("incident", "Incident"),
                    ("telegram", "Telegram"),
                ],
                default="manual",
                max_length=20,
            ),
        ),
    ]
