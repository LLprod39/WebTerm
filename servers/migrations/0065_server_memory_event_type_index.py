from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0064_server_memory_promotion"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="servermemoryevent",
            index=models.Index(
                fields=["server", "event_type", "-created_at"],
                name="mem_evt_server_type_time_idx",
            ),
        ),
    ]
