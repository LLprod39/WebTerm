from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0048_backfill_playbook_workspace"),
    ]

    operations = [
        migrations.AlterField(
            model_name="server",
            name="ai_read_only",
            field=models.BooleanField(
                default=True,
                help_text="AI-агент может только читать состояние сервера, но не выполнять изменяющие команды.",
            ),
        ),
    ]
