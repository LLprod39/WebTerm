from __future__ import annotations

from django.conf import settings
from django.db import models


class PluginPackage(models.Model):
    SOURCE_BUILTIN = "builtin"
    SOURCE_LOCAL = "local"
    SOURCE_CATALOG = "catalog"
    SOURCE_CHOICES = [
        (SOURCE_BUILTIN, "Built-in"),
        (SOURCE_LOCAL, "Local package"),
        (SOURCE_CATALOG, "Catalog"),
    ]

    REVIEW_PENDING = "pending"
    REVIEW_VERIFIED = "verified"
    REVIEW_REJECTED = "rejected"
    REVIEW_SUSPENDED = "suspended"
    REVIEW_CHOICES = [(REVIEW_PENDING, "Pending"), (REVIEW_VERIFIED, "Verified"), (REVIEW_REJECTED, "Rejected"), (REVIEW_SUSPENDED, "Suspended")]

    SIGNATURE_UNSIGNED = "unsigned"
    SIGNATURE_BUILTIN = "builtin"
    SIGNATURE_SIGNED = "signed"
    SIGNATURE_INVALID = "invalid"
    SIGNATURE_CHOICES = [(SIGNATURE_UNSIGNED, "Unsigned"), (SIGNATURE_BUILTIN, "Built-in"), (SIGNATURE_SIGNED, "Signed"), (SIGNATURE_INVALID, "Invalid")]

    plugin_id = models.CharField(max_length=140)
    version = models.CharField(max_length=80)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    publisher_id = models.CharField(max_length=120)
    publisher_name = models.CharField(max_length=160)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_BUILTIN)
    package_hash = models.CharField(max_length=128, blank=True, default="")
    signature_payload = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    attestations = models.JSONField(default=list, blank=True)
    sbom = models.JSONField(default=dict, blank=True)
    dependency_scan = models.JSONField(default=dict, blank=True)
    manifest = models.JSONField(default=dict)
    risk_tier = models.CharField(max_length=40, default="info")
    review_status = models.CharField(max_length=20, choices=REVIEW_CHOICES, default=REVIEW_PENDING)
    signature_status = models.CharField(max_length=20, choices=SIGNATURE_CHOICES, default=SIGNATURE_UNSIGNED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plugin_id", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["plugin_id", "version"], name="pm_pkg_plugin_version_uniq"),
        ]
        indexes = [
            models.Index(fields=["plugin_id"], name="pm_pkg_plugin_idx"),
            models.Index(fields=["source", "review_status"], name="pm_pkg_source_review_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.plugin_id}@{self.version}"


class PluginInstallation(models.Model):
    STATUS_DISABLED = "disabled"
    STATUS_ENABLED = "enabled"
    STATUS_BLOCKED = "blocked"
    STATUS_QUARANTINED = "quarantined"
    STATUS_UNINSTALLING = "uninstalling"
    STATUS_CHOICES = [
        (STATUS_DISABLED, "Disabled"),
        (STATUS_ENABLED, "Enabled"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_QUARANTINED, "Quarantined"),
        (STATUS_UNINSTALLING, "Uninstalling"),
    ]

    package = models.ForeignKey(PluginPackage, on_delete=models.PROTECT, related_name="installations")
    plugin_id = models.CharField(max_length=140, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DISABLED)
    installed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plugin_installations",
    )
    installed_at = models.DateTimeField(auto_now_add=True)
    enabled_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    scoped_groups = models.ManyToManyField(
        "auth.Group",
        blank=True,
        related_name="scoped_plugin_installations",
    )
    settings = models.JSONField(default=dict, blank=True)
    health_status = models.CharField(max_length=30, blank=True, default="")
    health_failure_count = models.PositiveIntegerField(default=0)
    last_health_check_at = models.DateTimeField(null=True, blank=True)
    quarantined_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["plugin_id"]
        indexes = [
            models.Index(fields=["status"], name="pm_install_status_idx"),
            models.Index(fields=["plugin_id", "status"], name="pm_install_plugin_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.plugin_id} [{self.status}]"


class PluginPermissionGrant(models.Model):
    installation = models.ForeignKey(PluginInstallation, on_delete=models.CASCADE, related_name="permission_grants")
    scope = models.CharField(max_length=160)
    reason = models.TextField(blank=True, default="")
    risk_tier = models.CharField(max_length=40, default="read")
    granted = models.BooleanField(default=False)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plugin_permission_grants",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["installation_id", "scope"]
        constraints = [
            models.UniqueConstraint(fields=["installation", "scope"], name="pm_permission_install_scope_uniq"),
        ]
        indexes = [
            models.Index(fields=["scope", "granted"], name="pm_perm_scope_grant_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.installation.plugin_id}:{self.scope}={self.granted}"


class PluginInstallEvent(models.Model):
    installation = models.ForeignKey(
        PluginInstallation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
    )
    plugin_id = models.CharField(max_length=140)
    event_type = models.CharField(max_length=80)
    status = models.CharField(max_length=20, default="info")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plugin_events",
    )
    message = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["plugin_id", "-created_at"], name="pm_event_plugin_created_idx"),
            models.Index(fields=["event_type", "-created_at"], name="pm_event_type_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.plugin_id}:{self.event_type}"


class MarketplaceSource(models.Model):
    name = models.CharField(max_length=160)
    source_url = models.CharField(max_length=500)
    is_enabled = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MarketplaceCatalogItem(models.Model):
    source = models.ForeignKey(MarketplaceSource, on_delete=models.CASCADE, related_name="items")
    plugin_id = models.CharField(max_length=140)
    version = models.CharField(max_length=80)
    manifest = models.JSONField(default=dict)
    package_url = models.CharField(max_length=500, blank=True, default="")
    compatibility = models.JSONField(default=dict, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=PluginPackage.REVIEW_CHOICES,
        default=PluginPackage.REVIEW_PENDING,
    )
    signature_status = models.CharField(
        max_length=20,
        choices=PluginPackage.SIGNATURE_CHOICES,
        default=PluginPackage.SIGNATURE_UNSIGNED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plugin_id", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["source", "plugin_id", "version"], name="pm_catalog_source_plugin_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.plugin_id}@{self.version} from {self.source_id}"


class PluginCompatibilityJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_PASSED, "Passed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_ERROR, "Error"),
    ]

    catalog_item = models.ForeignKey(MarketplaceCatalogItem, on_delete=models.CASCADE, related_name="compatibility_jobs")
    plugin_id = models.CharField(max_length=140)
    version = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    isolation_mode = models.CharField(max_length=80, default="in_process_no_code")
    checks = models.JSONField(default=list, blank=True)
    report = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["plugin_id", "-created_at"], name="pm_compat_plugin_created_idx"),
            models.Index(fields=["status", "-created_at"], name="pm_compat_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.plugin_id}@{self.version}:{self.status}"


from plugin_marketplace.access_models import PluginSecretBinding
