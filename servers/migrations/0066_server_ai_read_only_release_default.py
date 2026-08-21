from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0065_server_memory_event_type_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="server",
            name="ai_read_only",
            field=models.BooleanField(
                default=False,
                help_text="AI-агент может только читать состояние сервера, но не выполнять изменяющие команды.",
            ),
        ),
    ]
