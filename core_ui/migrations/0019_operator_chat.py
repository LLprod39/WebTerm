# Generated for Operator chat (ChatTurnState, ChatArtifact, session/action fields)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core_ui", "0018_add_kubernetes_secret_read_feature"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatsession",
            name="kind",
            field=models.CharField(
                choices=[("manual", "Manual"), ("duty", "Duty"), ("incident", "Incident")],
                default="manual",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="pinned_context",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="chatsession",
            name="total_usage",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="assistantaction",
            name="undo_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="assistantaction",
            name="dry_run_preview",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="assistantaction",
            name="blast_radius",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="assistantaction",
            name="async_run_ref",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.CreateModel(
            name="ChatArtifact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("ansible", "Ansible"),
                            ("script", "Script"),
                            ("report", "Report"),
                            ("chart", "Chart"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=30,
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("content", models.TextField(blank=True, default="")),
                ("version", models.PositiveIntegerField(default=1)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("saved_playbook_id", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="artifacts",
                        to="core_ui.chatmessage",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="artifacts",
                        to="core_ui.chatsession",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="ChatTurnState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("awaiting_confirm", "Awaiting confirm"),
                            ("resuming", "Resuming"),
                            ("done", "Done"),
                            ("failed", "Failed"),
                            ("limit", "Limit"),
                        ],
                        default="running",
                        max_length=30,
                    ),
                ),
                ("llm_messages", models.JSONField(blank=True, default=list)),
                ("pending_tool_call", models.JSONField(blank=True, default=dict)),
                ("iteration", models.PositiveIntegerField(default=0)),
                ("total_input_tokens", models.PositiveIntegerField(default=0)),
                ("total_output_tokens", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assistant_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="turn_states_as_assistant",
                        to="core_ui.chatmessage",
                    ),
                ),
                (
                    "pending_action",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="turn_states",
                        to="core_ui.assistantaction",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turn_states",
                        to="core_ui.chatsession",
                    ),
                ),
                (
                    "user_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="turn_states_as_user",
                        to="core_ui.chatmessage",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chatartifact",
            index=models.Index(fields=["session", "-updated_at"], name="cu_art_session_updated_idx"),
        ),
        migrations.AddIndex(
            model_name="chatturnstate",
            index=models.Index(fields=["session", "status"], name="cu_turn_session_status_idx"),
        ),
        migrations.AddIndex(
            model_name="chatturnstate",
            index=models.Index(fields=["session", "-updated_at"], name="cu_turn_session_updated_idx"),
        ),
    ]
