import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import mars.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MarsWorkspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("root_path", models.CharField(max_length=1024)),
                ("read_allow_roots", models.JSONField(blank=True, default=list)),
                ("write_allow_roots", models.JSONField(blank=True, default=list)),
                ("deny_globs", models.JSONField(blank=True, default=mars.models.default_deny_globs)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mars_workspaces",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["name", "id"],
                "indexes": [models.Index(fields=["user", "enabled", "name"], name="mars_marswo_user_id_191f23_idx")],
                "unique_together": {("user", "name")},
            },
        ),
        migrations.CreateModel(
            name="MarsSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task_brief", models.TextField()),
                ("answers", models.JSONField(blank=True, default=dict)),
                ("interview_questions", models.JSONField(blank=True, default=list)),
                ("selected_skill_slugs", models.JSONField(blank=True, default=list)),
                ("generated_plan", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("interview", "Interview"),
                            ("plan_ready", "Plan ready"),
                            ("approved", "Approved"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="interview",
                        max_length=24,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mars_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to="mars.marsworkspace",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
                "indexes": [
                    models.Index(fields=["user", "status", "-updated_at"], name="mars_marsse_user_id_6ff9c5_idx"),
                    models.Index(fields=["workspace", "-updated_at"], name="mars_marsse_workspa_239f48_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MarsRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cli_roles", models.JSONField(blank=True, default=mars.models.default_cli_roles)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("stopped", "Stopped"),
                        ],
                        default="queued",
                        max_length=24,
                    ),
                ),
                ("runtime_control", models.JSONField(blank=True, default=dict)),
                ("allow_dirty", models.BooleanField(default=False)),
                ("final_report", models.TextField(blank=True)),
                ("codex_summary", models.TextField(blank=True)),
                ("gemini_review", models.TextField(blank=True)),
                ("test_output", models.TextField(blank=True)),
                ("git_before", models.TextField(blank=True)),
                ("git_after", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runs",
                        to="mars.marssession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mars_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runs",
                        to="mars.marsworkspace",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["user", "status", "-created_at"], name="mars_marsru_user_id_22364f_idx"),
                    models.Index(fields=["status", "created_at"], name="mars_marsru_status_517a6f_idx"),
                    models.Index(fields=["session", "-created_at"], name="mars_marsru_session_14080d_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="MarsRunEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=80)),
                ("message", models.TextField(blank=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="mars.marsrun",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["run", "created_at"], name="mars_marsru_run_id_5da9e2_idx"),
                    models.Index(fields=["event_type", "created_at"], name="mars_marsru_event_t_f19c7f_idx"),
                ],
            },
        ),
    ]

