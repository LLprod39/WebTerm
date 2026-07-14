from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("servers", "0040_playbook_playbookrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="playbookrun",
            name="progress",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Live execution progress: current play/task, counters",
            ),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="live_log",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Streamed engine output (tail) updated while the run is active",
            ),
        ),
    ]
