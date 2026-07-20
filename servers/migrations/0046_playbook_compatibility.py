from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("servers", "0045_predictions_forecast_alerts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="playbook",
            name="compatibility",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Latest deterministic Ansible compatibility report",
            ),
        ),
        migrations.CreateModel(
            name="PlaybookCompatibilityRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_hash", models.CharField(max_length=64)),
                ("adapted_yaml", models.TextField()),
                ("inventory_bindings", models.JSONField(blank=True, default=dict)),
                ("report", models.JSONField(blank=True, default=dict)),
                ("semantic_guard", models.JSONField(blank=True, default=dict)),
                ("change_summary", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[("draft", "Draft"), ("validated", "Validated"), ("rejected", "Rejected")],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compatibility_revisions",
                        to="servers.playbook",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbook_compatibility_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="playbookcompatibilityrevision",
            index=models.Index(fields=["playbook", "-created_at"], name="servers_pla_playboo_compat_idx"),
        ),
        migrations.AddField(
            model_name="playbook",
            name="active_compatibility_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_for_playbooks",
                to="servers.playbookcompatibilityrevision",
            ),
        ),
    ]
