from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0019_serverwatcherdraft"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentRunEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=80)),
                ("task_id", models.IntegerField(blank=True, null=True)),
                ("message", models.TextField(blank=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="servers.agentrun"),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="agentrunevent",
            index=models.Index(fields=["run", "created_at"], name="servers_age_run_id_5d9331_idx"),
        ),
        migrations.AddIndex(
            model_name="agentrunevent",
            index=models.Index(fields=["event_type", "created_at"], name="servers_age_event_t_57c2a0_idx"),
        ),
    ]
