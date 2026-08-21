import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core_ui", "0028_ai_provider_pilot_safety"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("servers", "0061_backgroundworkerstate_ai_provider_auth"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServerMemoryGenerationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "generation_kind",
                    models.CharField(
                        choices=[
                            ("distillation", "Memory Distillation"),
                            ("pattern_enhancement", "Pattern Enhancement"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("started", "Started"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("fallback", "Heuristic Fallback"),
                        ],
                        default="started",
                        max_length=20,
                    ),
                ),
                ("model_alias", models.CharField(blank=True, default="", max_length=80)),
                ("prompt_template_key", models.CharField(blank=True, default="", max_length=80)),
                ("prompt_template_version", models.CharField(blank=True, default="", max_length=32)),
                ("prompt_sha256", models.CharField(db_index=True, max_length=64)),
                ("output_sha256", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("prompt_redacted_ref", models.CharField(blank=True, default="", max_length=255)),
                ("output_redacted_ref", models.CharField(blank=True, default="", max_length=255)),
                ("error_code", models.CharField(blank=True, default="", max_length=80)),
                ("error_redacted_ref", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "invocation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="server_memory_generation_logs",
                        to="core_ui.aiproviderinvocation",
                    ),
                ),
                (
                    "server",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory_generation_logs",
                        to="servers.server",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddField(
            model_name="servermemorysnapshot",
            name="content_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="servermemorysnapshot",
            name="generation_log",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="snapshots",
                to="servers.servermemorygenerationlog",
            ),
        ),
        migrations.AddField(
            model_name="servermemoryrevalidation",
            name="decided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servermemoryrevalidation",
            name="decided_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="server_memory_revalidation_decisions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="servermemoryrevalidation",
            name="decision_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddIndex(
            model_name="servermemorygenerationlog",
            index=models.Index(
                fields=["server", "generation_kind", "-created_at"],
                name="servers_ser_server__c74c46_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servermemorygenerationlog",
            index=models.Index(fields=["status", "-created_at"], name="servers_ser_status_f19528_idx"),
        ),
    ]
