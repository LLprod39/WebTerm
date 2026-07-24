import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("core_ui", "0006_desktoprefreshtoken_managedsecret"),
        ("servers", "0046_playbook_compatibility"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="playbook",
            name="is_archived",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="PlaybookAssetBundle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("storage_key", models.CharField(max_length=500, unique=True)),
                ("manifest", models.JSONField(blank=True, default=list)),
                ("content_hash", models.CharField(db_index=True, max_length=64)),
                ("size_bytes", models.BigIntegerField(default=0)),
                ("file_count", models.PositiveIntegerField(default=0)),
                (
                    "scan_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("clean", "Clean"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("scan_report", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_playbook_asset_bundles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["scan_status", "-created_at"], name="pb_bundle_scan_created_idx")],
            },
        ),
        migrations.CreateModel(
            name="PlaybookAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=80)),
                ("entity_type", models.CharField(blank=True, default="playbook", max_length=40)),
                ("entity_id", models.CharField(blank=True, default="", max_length=80)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="playbook_audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                        to="servers.playbook",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["playbook", "-created_at"], name="pb_audit_playbook_created_idx"),
                    models.Index(fields=["event_type", "-created_at"], name="pb_audit_event_created_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PlaybookBindingProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("is_default", models.BooleanField(default=False)),
                ("selector_mappings", models.JSONField(blank=True, default=dict)),
                ("variable_values", models.JSONField(blank=True, default=dict)),
                ("secret_references", models.JSONField(blank=True, default=dict)),
                ("options", models.JSONField(blank=True, default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
                ("content_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="binding_profiles",
                        to="servers.playbook",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbook_binding_profiles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-is_default", "name", "id"],
                "indexes": [models.Index(fields=["playbook", "user", "-updated_at"], name="pb_binding_owner_updated_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("playbook", "user", "name"), name="uniq_playbook_binding_name"),
                    models.UniqueConstraint(
                        condition=models.Q(is_default=True),
                        fields=("playbook", "user"),
                        name="uniq_default_playbook_binding",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PlaybookGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("viewer", "Viewer"),
                            ("editor", "Editor"),
                            ("operator", "Operator"),
                            ("manager", "Manager"),
                        ],
                        default="viewer",
                        max_length=20,
                    ),
                ),
                ("can_view", models.BooleanField(default=True)),
                ("can_edit", models.BooleanField(default=False)),
                ("can_validate", models.BooleanField(default=False)),
                ("can_publish", models.BooleanField(default=False)),
                ("can_run", models.BooleanField(default=False)),
                ("can_export", models.BooleanField(default=False)),
                ("can_manage_shares", models.BooleanField(default=False)),
                (
                    "workspace_shared",
                    models.BooleanField(
                        default=False,
                        help_text="Legacy-compatible grant to every authenticated workspace user.",
                    ),
                ),
                (
                    "is_legacy",
                    models.BooleanField(
                        default=False,
                        help_text="Marks a compatibility grant migrated from visibility=shared.",
                    ),
                ),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "granted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="issued_playbook_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbook_grants",
                        to="auth.group",
                    ),
                ),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grants",
                        to="servers.playbook",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbook_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["user", "revoked_at", "expires_at"], name="pb_grant_user_active_idx"),
                    models.Index(fields=["group", "revoked_at", "expires_at"], name="pb_grant_group_active_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            (models.Q(user__isnull=False) & models.Q(group__isnull=True) & models.Q(workspace_shared=False))
                            | (models.Q(user__isnull=True) & models.Q(group__isnull=False) & models.Q(workspace_shared=False))
                            | (models.Q(user__isnull=True) & models.Q(group__isnull=True) & models.Q(workspace_shared=True))
                        ),
                        name="playbook_grant_exactly_one_principal",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(user__isnull=False),
                        fields=("playbook", "user"),
                        name="uniq_playbook_user_grant",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(group__isnull=False),
                        fields=("playbook", "group"),
                        name="uniq_playbook_group_grant",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(workspace_shared=True),
                        fields=("playbook",),
                        name="uniq_playbook_workspace_grant",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PlaybookRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision_number", models.PositiveIntegerField()),
                (
                    "content_format",
                    models.CharField(
                        choices=[("ansible_yaml", "Ansible YAML"), ("runbook_json", "Runbook JSON")],
                        max_length=30,
                    ),
                ),
                ("source_yaml", models.TextField(blank=True, default="")),
                ("tasks", models.JSONField(blank=True, default=list)),
                ("content_hash", models.CharField(db_index=True, max_length=64)),
                ("bundle_hash", models.CharField(blank=True, default="", max_length=64)),
                (
                    "origin_type",
                    models.CharField(
                        choices=[
                            ("imported", "Imported"),
                            ("manual", "Manual"),
                            ("guided", "Guided"),
                            ("template", "Template"),
                            ("adaptation", "Adaptation"),
                            ("conversion", "Conversion"),
                            ("rollback", "Rollback"),
                        ],
                        default="manual",
                        max_length=30,
                    ),
                ),
                ("message", models.CharField(blank=True, default="", max_length=500)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "asset_bundle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="revisions",
                        to="servers.playbookassetbundle",
                    ),
                ),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="authored_playbook_revisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="servers.playbookrevision",
                    ),
                ),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_revisions",
                        to="servers.playbook",
                    ),
                ),
            ],
            options={
                "ordering": ["-revision_number"],
                "indexes": [
                    models.Index(fields=["playbook", "-revision_number"], name="pb_revision_number_idx"),
                    models.Index(fields=["playbook", "content_hash"], name="pb_revision_hash_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("playbook", "revision_number"),
                        name="uniq_playbook_revision_number",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PlaybookDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "content_format",
                    models.CharField(
                        choices=[("ansible_yaml", "Ansible YAML"), ("runbook_json", "Runbook JSON")],
                        max_length=30,
                    ),
                ),
                ("source_yaml", models.TextField(blank=True, default="")),
                ("tasks", models.JSONField(blank=True, default=list)),
                ("content_hash", models.CharField(max_length=64)),
                ("bundle_hash", models.CharField(blank=True, default="", max_length=64)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "asset_bundle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="drafts",
                        to="servers.playbookassetbundle",
                    ),
                ),
                (
                    "base_revision",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="based_drafts",
                        to="servers.playbookrevision",
                    ),
                ),
                (
                    "last_editor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="edited_playbook_drafts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "playbook",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="draft",
                        to="servers.playbook",
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["last_editor", "-updated_at"], name="pb_draft_editor_updated_idx")],
            },
        ),
        migrations.AddField(
            model_name="playbook",
            name="forked_from_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="forked_playbooks",
                to="servers.playbookrevision",
            ),
        ),
        migrations.AddField(
            model_name="playbook",
            name="origin_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="origin_for_playbooks",
                to="servers.playbookrevision",
            ),
        ),
        migrations.AddField(
            model_name="playbook",
            name="published_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="published_for_playbooks",
                to="servers.playbookrevision",
            ),
        ),
        migrations.AddField(
            model_name="playbookcompatibilityrevision",
            name="result_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="legacy_compatibility_outputs",
                to="servers.playbookrevision",
            ),
        ),
        migrations.AddField(
            model_name="playbookcompatibilityrevision",
            name="source_revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="legacy_compatibility_inputs",
                to="servers.playbookrevision",
            ),
        ),
        migrations.CreateModel(
            name="PlaybookValidation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("analyzer_version", models.CharField(max_length=80)),
                ("runtime_fingerprint", models.JSONField(blank=True, default=dict)),
                ("runtime_fingerprint_hash", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("target_signature", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("binding_version", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("ready", "Ready"),
                            ("blocked", "Blocked"),
                            ("stale", "Stale"),
                            ("error", "Error"),
                        ],
                        default="running",
                        max_length=20,
                    ),
                ),
                ("stages", models.JSONField(blank=True, default=dict)),
                ("issues", models.JSONField(blank=True, default=list)),
                ("stale_reason", models.CharField(blank=True, default="", max_length=300)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "binding_profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="validations",
                        to="servers.playbookbindingprofile",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requested_playbook_validations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="validations",
                        to="servers.playbookrevision",
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["revision", "status", "-started_at"], name="pb_validation_status_idx"),
                    models.Index(fields=["requested_by", "-started_at"], name="pb_validation_user_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="binding_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="runs",
                to="servers.playbookbindingprofile",
            ),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="execution_fingerprint",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="revision",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="runs",
                to="servers.playbookrevision",
            ),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="terminal_notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="terminal_notification_claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="terminal_notification_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="terminal_notification_last_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="validation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="runs",
                to="servers.playbookvalidation",
            ),
        ),
        migrations.AddField(
            model_name="playbookrun",
            name="variable_manifest",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Redacted variable names and managed-secret references; never raw secret values.",
            ),
        ),
        migrations.CreateModel(
            name="PlaybookRunDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("claimed", "Claimed"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("canceled", "Canceled"),
                            ("interrupted", "Interrupted"),
                        ],
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("queued_at", models.DateTimeField(auto_now_add=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("claimed_by", models.CharField(blank=True, default="", max_length=120)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                (
                    "mutation_safe_to_retry",
                    models.BooleanField(
                        default=False,
                        help_text="Must be explicitly true before an expired claim may be requeued.",
                    ),
                ),
                (
                    "run",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dispatch",
                        to="servers.playbookrun",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="playbook_run_dispatches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["queued_at", "id"],
                "indexes": [
                    models.Index(fields=["status", "queued_at"], name="pb_dispatch_queue_idx"),
                    models.Index(fields=["status", "lease_expires_at"], name="pb_dispatch_lease_idx"),
                ],
            },
        ),
    ]
