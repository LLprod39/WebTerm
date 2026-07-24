"""Revisioned playbook workspace models.

The legacy fields on :class:`servers.models.Playbook` stay available during the
dual-read/dual-write migration.  New code stores editable content in a draft
and publishes immutable revisions from that draft.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class PlaybookAssetBundle(models.Model):
    """Metadata for a playbook project archive kept in artifact storage."""

    SCAN_PENDING = "pending"
    SCAN_CLEAN = "clean"
    SCAN_REJECTED = "rejected"
    SCAN_FAILED = "failed"
    SCAN_STATUS_CHOICES = [
        (SCAN_PENDING, "Pending"),
        (SCAN_CLEAN, "Clean"),
        (SCAN_REJECTED, "Rejected"),
        (SCAN_FAILED, "Failed"),
    ]

    storage_key = models.CharField(max_length=500, unique=True)
    manifest = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    size_bytes = models.BigIntegerField(default=0)
    file_count = models.PositiveIntegerField(default=0)
    scan_status = models.CharField(max_length=20, choices=SCAN_STATUS_CHOICES, default=SCAN_PENDING)
    scan_report = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_playbook_asset_bundles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["scan_status", "-created_at"], name="pb_bundle_scan_created_idx")]


class PlaybookRevision(models.Model):
    """Immutable, executable snapshot of playbook content."""

    FORMAT_ANSIBLE_YAML = "ansible_yaml"
    FORMAT_RUNBOOK_JSON = "runbook_json"
    FORMAT_CHOICES = [
        (FORMAT_ANSIBLE_YAML, "Ansible YAML"),
        (FORMAT_RUNBOOK_JSON, "Runbook JSON"),
    ]

    ORIGIN_IMPORTED = "imported"
    ORIGIN_MANUAL = "manual"
    ORIGIN_GUIDED = "guided"
    ORIGIN_TEMPLATE = "template"
    ORIGIN_ADAPTATION = "adaptation"
    ORIGIN_CONVERSION = "conversion"
    ORIGIN_ROLLBACK = "rollback"
    ORIGIN_CHOICES = [
        (ORIGIN_IMPORTED, "Imported"),
        (ORIGIN_MANUAL, "Manual"),
        (ORIGIN_GUIDED, "Guided"),
        (ORIGIN_TEMPLATE, "Template"),
        (ORIGIN_ADAPTATION, "Adaptation"),
        (ORIGIN_CONVERSION, "Conversion"),
        (ORIGIN_ROLLBACK, "Rollback"),
    ]

    playbook = models.ForeignKey("Playbook", on_delete=models.CASCADE, related_name="content_revisions")
    revision_number = models.PositiveIntegerField()
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_playbook_revisions",
    )
    content_format = models.CharField(max_length=30, choices=FORMAT_CHOICES)
    source_yaml = models.TextField(blank=True, default="")
    tasks = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    asset_bundle = models.ForeignKey(
        PlaybookAssetBundle,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="revisions",
    )
    bundle_hash = models.CharField(max_length=64, blank=True, default="")
    origin_type = models.CharField(max_length=30, choices=ORIGIN_CHOICES, default=ORIGIN_MANUAL)
    message = models.CharField(max_length=500, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["playbook", "revision_number"],
                name="uniq_playbook_revision_number",
            )
        ]
        indexes = [
            models.Index(fields=["playbook", "-revision_number"], name="pb_revision_number_idx"),
            models.Index(fields=["playbook", "content_hash"], name="pb_revision_hash_idx"),
        ]

    def __str__(self) -> str:
        return f"Playbook {self.playbook_id} revision {self.revision_number}"

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise ValidationError("Playbook revisions are immutable; create a new revision instead")
        return super().save(*args, **kwargs)


class PlaybookDraft(models.Model):
    """Single optimistic-lock protected working copy for a playbook."""

    playbook = models.OneToOneField("Playbook", on_delete=models.CASCADE, related_name="draft")
    base_revision = models.ForeignKey(
        PlaybookRevision,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="based_drafts",
    )
    content_format = models.CharField(max_length=30, choices=PlaybookRevision.FORMAT_CHOICES)
    source_yaml = models.TextField(blank=True, default="")
    tasks = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64)
    asset_bundle = models.ForeignKey(
        PlaybookAssetBundle,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="drafts",
    )
    bundle_hash = models.CharField(max_length=64, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_playbook_drafts",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["last_editor", "-updated_at"], name="pb_draft_editor_updated_idx")]


class PlaybookValidation(models.Model):
    """Context-bound validation evidence for one immutable revision."""

    STATUS_RUNNING = "running"
    STATUS_READY = "ready"
    STATUS_BLOCKED = "blocked"
    STATUS_STALE = "stale"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_READY, "Ready"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_STALE, "Stale"),
        (STATUS_ERROR, "Error"),
    ]

    revision = models.ForeignKey(PlaybookRevision, on_delete=models.CASCADE, related_name="validations")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_playbook_validations",
    )
    analyzer_version = models.CharField(max_length=80)
    runtime_fingerprint = models.JSONField(default=dict, blank=True)
    runtime_fingerprint_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    target_signature = models.CharField(max_length=64, blank=True, default="", db_index=True)
    binding_profile = models.ForeignKey(
        "PlaybookBindingProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validations",
    )
    binding_version = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    stages = models.JSONField(default=dict, blank=True)
    issues = models.JSONField(default=list, blank=True)
    stale_reason = models.CharField(max_length=300, blank=True, default="")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["revision", "status", "-started_at"], name="pb_validation_status_idx"),
            models.Index(fields=["requested_by", "-started_at"], name="pb_validation_user_idx"),
        ]


class PlaybookBindingProfile(models.Model):
    """Viewer-owned inventory mappings and non-secret runtime presets."""

    playbook = models.ForeignKey("Playbook", on_delete=models.CASCADE, related_name="binding_profiles")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="playbook_binding_profiles",
    )
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)
    selector_mappings = models.JSONField(default=dict, blank=True)
    variable_values = models.JSONField(default=dict, blank=True)
    secret_references = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["playbook", "user", "name"], name="uniq_playbook_binding_name"),
            models.UniqueConstraint(
                fields=["playbook", "user"],
                condition=models.Q(is_default=True),
                name="uniq_default_playbook_binding",
            ),
        ]
        indexes = [models.Index(fields=["playbook", "user", "-updated_at"], name="pb_binding_owner_updated_idx")]


class PlaybookGrant(models.Model):
    """Explicit per-user or per-group capability grant for a playbook."""

    ROLE_VIEWER = "viewer"
    ROLE_EDITOR = "editor"
    ROLE_OPERATOR = "operator"
    ROLE_MANAGER = "manager"
    ROLE_CHOICES = [
        (ROLE_VIEWER, "Viewer"),
        (ROLE_EDITOR, "Editor"),
        (ROLE_OPERATOR, "Operator"),
        (ROLE_MANAGER, "Manager"),
    ]

    playbook = models.ForeignKey("Playbook", on_delete=models.CASCADE, related_name="grants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="playbook_grants",
    )
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="playbook_grants",
    )
    workspace_shared = models.BooleanField(
        default=False,
        help_text="Legacy-compatible grant to every authenticated workspace user.",
    )
    is_legacy = models.BooleanField(
        default=False,
        help_text="Marks a compatibility grant migrated from visibility=shared.",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=False)
    can_validate = models.BooleanField(default=False)
    can_publish = models.BooleanField(default=False)
    can_run = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_manage_shares = models.BooleanField(default=False)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_playbook_grants",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(user__isnull=False) & models.Q(group__isnull=True) & models.Q(workspace_shared=False))
                    | (models.Q(user__isnull=True) & models.Q(group__isnull=False) & models.Q(workspace_shared=False))
                    | (models.Q(user__isnull=True) & models.Q(group__isnull=True) & models.Q(workspace_shared=True))
                ),
                name="playbook_grant_exactly_one_principal",
            ),
            models.UniqueConstraint(
                fields=["playbook", "user"],
                condition=models.Q(user__isnull=False),
                name="uniq_playbook_user_grant",
            ),
            models.UniqueConstraint(
                fields=["playbook", "group"],
                condition=models.Q(group__isnull=False),
                name="uniq_playbook_group_grant",
            ),
            models.UniqueConstraint(
                fields=["playbook"],
                condition=models.Q(workspace_shared=True),
                name="uniq_playbook_workspace_grant",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "revoked_at", "expires_at"], name="pb_grant_user_active_idx"),
            models.Index(fields=["group", "revoked_at", "expires_at"], name="pb_grant_group_active_idx"),
        ]

    @property
    def principal_label(self) -> str:
        if self.user_id:
            return self.user.get_username()
        if self.group_id:
            return self.group.name
        if self.workspace_shared:
            return "Workspace"
        return ""


class PlaybookAuditEvent(models.Model):
    """Append-only object audit trail without secret payloads."""

    playbook = models.ForeignKey("Playbook", on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="playbook_audit_events",
    )
    event_type = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=40, blank=True, default="playbook")
    entity_id = models.CharField(max_length=80, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["playbook", "-created_at"], name="pb_audit_playbook_created_idx"),
            models.Index(fields=["event_type", "-created_at"], name="pb_audit_event_created_idx"),
        ]
