from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("servers", "0039_memory_trust_gate"),
    ]

    operations = [
        migrations.CreateModel(
            name="Playbook",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "kind",
                    models.CharField(
                        choices=[("runbook", "Runbook"), ("ansible", "Ansible")],
                        default="runbook",
                        max_length=20,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("deploy", "Deploy"),
                            ("patch", "Patch"),
                            ("diagnose", "Diagnose"),
                            ("security", "Security"),
                            ("maintenance", "Maintenance"),
                            ("custom", "Custom"),
                        ],
                        default="custom",
                        max_length=30,
                    ),
                ),
                (
                    "visibility",
                    models.CharField(
                        choices=[("private", "Private"), ("shared", "Shared")],
                        default="private",
                        max_length=20,
                    ),
                ),
                ("tasks", models.JSONField(blank=True, default=list, help_text="Ordered task list")),
                (
                    "source_yaml",
                    models.TextField(blank=True, default="", help_text="Original Ansible YAML if imported"),
                ),
                ("tags", models.JSONField(blank=True, default=list)),
                (
                    "fidelity",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Import fidelity: runnable/total/unsupported modules",
                    ),
                ),
                ("is_template_clone", models.BooleanField(default=False)),
                ("template_slug", models.CharField(blank=True, default="", max_length=80)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_status", models.CharField(blank=True, default="", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbooks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="PlaybookRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("partial", "Partial"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("playbook_snapshot", models.JSONField(blank=True, default=dict)),
                ("target_server_ids", models.JSONField(blank=True, default=list)),
                ("target_group_ids", models.JSONField(blank=True, default=list)),
                ("options", models.JSONField(blank=True, default=dict)),
                ("host_results", models.JSONField(blank=True, default=list)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("inventory_preview", models.TextField(blank=True, default="")),
                ("cancel_requested", models.BooleanField(default=False)),
                ("error_message", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "playbook",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="runs",
                        to="servers.playbook",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbook_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="playbook",
            index=models.Index(fields=["user", "-updated_at"], name="servers_pla_user_id_7c0d0a_idx"),
        ),
        migrations.AddIndex(
            model_name="playbook",
            index=models.Index(fields=["user", "category"], name="servers_pla_user_id_cat_idx"),
        ),
        migrations.AddIndex(
            model_name="playbook",
            index=models.Index(fields=["visibility", "-updated_at"], name="servers_pla_visib_upd_idx"),
        ),
        migrations.AddIndex(
            model_name="playbookrun",
            index=models.Index(fields=["user", "-created_at"], name="servers_pr_user_id_crt_idx"),
        ),
        migrations.AddIndex(
            model_name="playbookrun",
            index=models.Index(fields=["status", "-created_at"], name="servers_pr_status_crt_idx"),
        ),
        migrations.AddIndex(
            model_name="playbookrun",
            index=models.Index(fields=["playbook", "-created_at"], name="servers_pr_pb_crt_idx"),
        ),
    ]
