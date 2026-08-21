import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core_ui", "0028_ai_provider_pilot_safety"),
        ("servers", "0062_server_memory_generation_provenance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ServerMemoryAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("stable_key", models.CharField(max_length=120)),
                (
                    "asset_kind",
                    models.CharField(
                        choices=[
                            ("note", "Note"),
                            ("runbook", "Runbook"),
                            ("decision", "Decision"),
                            ("pattern", "Pattern"),
                        ],
                        default="note",
                        max_length=24,
                    ),
                ),
                (
                    "visibility",
                    models.CharField(
                        choices=[
                            ("inherit_server", "Inherit Server Context Access"),
                            ("private", "Private"),
                            ("project", "Project"),
                            ("restricted", "Restricted by Explicit Grants"),
                            ("agent", "Bound Agent Only"),
                        ],
                        default="inherit_server",
                        max_length=24,
                    ),
                ),
                (
                    "lifecycle",
                    models.CharField(
                        choices=[
                            ("candidate", "Candidate"),
                            ("approved", "Approved"),
                            ("deprecated", "Deprecated"),
                            ("archived", "Archived"),
                        ],
                        default="candidate",
                        max_length=20,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("source_ref", models.CharField(blank=True, default="", max_length=255)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_server_memory_assets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_server_memory_assets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "current_snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="current_for_assets",
                        to="servers.servermemorysnapshot",
                    ),
                ),
                (
                    "generation_log",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="servers.servermemorygenerationlog",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="server_memory_assets",
                        to="core_ui.project",
                    ),
                ),
                (
                    "server",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory_assets",
                        to="servers.server",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
        migrations.AddField(
            model_name="servermemorysnapshot",
            name="asset",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="snapshots",
                to="servers.servermemoryasset",
            ),
        ),
        migrations.CreateModel(
            name="ServerMemoryAssetAgentBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "injection_mode",
                    models.CharField(
                        choices=[("summary", "Summary"), ("reference", "Reference"), ("tool", "Tool")],
                        default="reference",
                        max_length=20,
                    ),
                ),
                ("priority", models.PositiveSmallIntegerField(default=100)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memory_asset_bindings",
                        to="servers.serveragent",
                    ),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_bindings",
                        to="servers.servermemoryasset",
                    ),
                ),
                (
                    "bound_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="server_memory_asset_bindings_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "pinned_snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pinned_memory_asset_bindings",
                        to="servers.servermemorysnapshot",
                    ),
                ),
            ],
            options={"ordering": ["asset_id", "agent_id"]},
        ),
        migrations.CreateModel(
            name="ServerMemoryAssetGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "permission",
                    models.CharField(
                        choices=[("read", "Read"), ("use", "Use"), ("manage", "Manage"), ("share", "Share")],
                        default="read",
                        max_length=16,
                    ),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grants",
                        to="servers.servermemoryasset",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="issued_server_memory_asset_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="server_memory_asset_grants",
                        to="auth.group",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="server_memory_asset_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["asset_id", "id"]},
        ),
        migrations.CreateModel(
            name="ServerMemoryRetrievalAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("query_sha256", models.CharField(db_index=True, max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[("succeeded", "Succeeded"), ("denied", "Denied"), ("error", "Error")],
                        default="succeeded",
                        max_length=20,
                    ),
                ),
                ("include_candidates", models.BooleanField(default=False)),
                ("requested_server_count", models.PositiveIntegerField(default=0)),
                ("accessible_server_count", models.PositiveIntegerField(default=0)),
                ("result_count", models.PositiveIntegerField(default=0)),
                ("returned_char_count", models.PositiveIntegerField(default=0)),
                ("requested_top_k", models.PositiveIntegerField(default=0)),
                ("requested_char_budget", models.PositiveIntegerField(default=0)),
                ("result_refs", models.JSONField(blank=True, default=list)),
                ("error_code", models.CharField(blank=True, default="", max_length=80)),
                ("duration_ms", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="memory_retrieval_audits",
                        to="servers.serveragent",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="server_memory_retrieval_audits",
                        to="core_ui.project",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="server_memory_retrieval_audits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="servermemoryasset",
            index=models.Index(
                fields=["project", "server", "lifecycle", "-updated_at"],
                name="servers_ser_project_9f3af2_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servermemoryasset",
            index=models.Index(
                fields=["visibility", "lifecycle", "-updated_at"],
                name="servers_ser_visibil_3dee6a_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="servermemoryasset",
            constraint=models.UniqueConstraint(
                fields=("server", "stable_key"),
                name="servers_mem_asset_unique_stable_key",
            ),
        ),
        migrations.AddConstraint(
            model_name="servermemoryassetagentbinding",
            constraint=models.UniqueConstraint(
                fields=("asset", "agent"),
                name="servers_mem_asset_unique_agent_binding",
            ),
        ),
        migrations.AddConstraint(
            model_name="servermemoryassetgrant",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("group__isnull", True), ("user__isnull", False)),
                    models.Q(("group__isnull", False), ("user__isnull", True)),
                    _connector="OR",
                ),
                name="servers_mem_asset_grant_one_subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="servermemoryassetgrant",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("asset", "user", "permission"),
                name="servers_mem_asset_unique_user_grant",
            ),
        ),
        migrations.AddConstraint(
            model_name="servermemoryassetgrant",
            constraint=models.UniqueConstraint(
                condition=models.Q(("group__isnull", False)),
                fields=("asset", "group", "permission"),
                name="servers_mem_asset_unique_group_grant",
            ),
        ),
        migrations.AddIndex(
            model_name="servermemoryretrievalaudit",
            index=models.Index(
                fields=["user", "project", "-created_at"],
                name="servers_ser_user_id_b97aac_idx",
            ),
        ),
    ]
