"""Persistent provider connections, routing preferences, pools, and audit."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models import Q

from app.ai_runtime import ExecutionMode, ProviderTarget

SUBSCRIPTION_TARGET_CHOICES = [
    (ProviderTarget.CODEX_SUBSCRIPTION.value, "Codex subscription"),
    (ProviderTarget.GROK_SUBSCRIPTION.value, "Grok subscription"),
]
ALL_TARGET_CHOICES = [(target.value, target.value) for target in ProviderTarget]


class AIProviderConnection(models.Model):
    """A personal or workspace-owned isolated CLI credential boundary."""

    SCOPE_PERSONAL = "personal"
    SCOPE_WORKSPACE = "workspace"
    SCOPE_CHOICES = [(SCOPE_PERSONAL, "Personal"), (SCOPE_WORKSPACE, "Workspace")]

    STATUS_PENDING_AUTH = "pending_auth"
    STATUS_CONNECTED = "connected"
    STATUS_AUTH_REQUIRED = "auth_required"
    STATUS_LIMITED = "limited"
    STATUS_DEGRADED = "degraded"
    STATUS_DISABLED = "disabled"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_PENDING_AUTH, "Pending authentication"),
        (STATUS_CONNECTED, "Connected"),
        (STATUS_AUTH_REQUIRED, "Authentication required"),
        (STATUS_LIMITED, "Limited"),
        (STATUS_DEGRADED, "Degraded"),
        (STATUS_DISABLED, "Disabled"),
        (STATUS_REVOKED, "Revoked"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    target_id = models.CharField(max_length=64, choices=SUBSCRIPTION_TARGET_CHOICES)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_provider_connections",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_ai_provider_connections",
    )
    name = models.CharField(max_length=120)
    credential_ref = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING_AUTH)
    enabled = models.BooleanField(default=True)
    runtime_version = models.CharField(max_length=80, blank=True, default="")
    auth_revision = models.PositiveIntegerField(default=0)
    concurrency_limit = models.PositiveSmallIntegerField(default=1)
    health = models.JSONField(default=dict, blank=True)
    limits = models.JSONField(default=dict, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True, default="")
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope", "name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(scope="personal", owner__isnull=False) | Q(scope="workspace", owner__isnull=True)),
                name="cu_ai_conn_scope_owner",
            ),
            models.CheckConstraint(condition=Q(concurrency_limit__gte=1), name="cu_ai_conn_concurrency_gte1"),
        ]
        indexes = [
            models.Index(fields=["owner", "enabled", "status"], name="cu_ai_conn_owner_status"),
            models.Index(fields=["scope", "target_id", "enabled"], name="cu_ai_conn_scope_target"),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.target_id}:{self.name}"


class AIConnectionAuthFlow(models.Model):
    """Auditable device-code login lifecycle without provider tokens."""

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_FAILED, "Failed"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    connection = models.ForeignKey(AIProviderConnection, on_delete=models.CASCADE, related_name="auth_flows")
    flow_kind = models.CharField(max_length=40, default="device_code")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verification_uri = models.URLField(max_length=500, blank=True, default="")
    user_code = models.CharField(max_length=64, blank=True, default="")
    error_code = models.CharField(max_length=80, blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=120, blank=True, default="")
    fencing_token = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection"],
                condition=Q(status="pending"),
                name="cu_ai_auth_one_pending_conn",
            )
        ]


class AIProviderPool(models.Model):
    """Admin-managed workspace pool; a member is pinned per invocation."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120, unique=True)
    target_id = models.CharField(max_length=64, choices=SUBSCRIPTION_TARGET_CHOICES)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_ai_provider_pools",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]


class AIProviderPoolMember(models.Model):
    pool = models.ForeignKey(AIProviderPool, on_delete=models.CASCADE, related_name="members")
    connection = models.ForeignKey(AIProviderConnection, on_delete=models.CASCADE, related_name="pool_memberships")
    enabled = models.BooleanField(default=True)
    weight = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["pool", "connection"], name="cu_ai_pool_unique_member"),
            models.CheckConstraint(condition=Q(weight__gte=1), name="cu_ai_pool_weight_gte1"),
        ]
        indexes = [models.Index(fields=["pool", "enabled"], name="cu_ai_pool_member_enabled")]


class AIProviderConnectionGrant(models.Model):
    """Default-deny grant to one user, auth group, or project role."""

    connection = models.ForeignKey(AIProviderConnection, on_delete=models.CASCADE, related_name="grants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_provider_connection_grants",
    )
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.CASCADE, related_name="ai_provider_grants")
    project = models.ForeignKey(
        "core_ui.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_provider_connection_grants",
    )
    project_role = models.CharField(max_length=20, blank=True, default="")
    allow_interactive = models.BooleanField(default=True)
    allow_unattended = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, group__isnull=True, project__isnull=True, project_role="")
                    | Q(user__isnull=True, group__isnull=False, project__isnull=True, project_role="")
                    | Q(user__isnull=True, group__isnull=True, project__isnull=False)
                ),
                name="cu_ai_grant_one_principal",
            ),
            models.UniqueConstraint(
                fields=["connection", "user"],
                condition=Q(user__isnull=False),
                name="cu_ai_grant_unique_user",
            ),
            models.UniqueConstraint(
                fields=["connection", "group"],
                condition=Q(group__isnull=False),
                name="cu_ai_grant_unique_group",
            ),
            models.UniqueConstraint(
                fields=["connection", "project", "project_role"],
                condition=Q(project__isnull=False),
                name="cu_ai_grant_unique_project_role",
            ),
        ]
        indexes = [models.Index(fields=["connection", "project"], name="cu_ai_grant_conn_project")]


class AIProviderPreference(models.Model):
    """Per-purpose user or workspace default provider binding."""

    PURPOSE_ASSISTANT = "assistant"
    PURPOSE_AGENTS = "agents"
    PURPOSE_TERMINAL = "terminal"
    PURPOSE_INTERNAL = "internal"
    PURPOSE_CHOICES = [
        (PURPOSE_ASSISTANT, "Assistant"),
        (PURPOSE_AGENTS, "Agents"),
        (PURPOSE_TERMINAL, "Terminal"),
        (PURPOSE_INTERNAL, "Internal"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_provider_preferences",
    )
    project = models.ForeignKey(
        "core_ui.Project",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ai_provider_preferences",
    )
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    target_id = models.CharField(max_length=64, choices=ALL_TARGET_CHOICES)
    connection = models.ForeignKey(
        AIProviderConnection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    pool = models.ForeignKey(
        AIProviderPool,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    model_id = models.CharField(max_length=120, blank=True, default="")
    reasoning_effort = models.CharField(max_length=16, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False) | Q(user__isnull=True, project__isnull=False)),
                name="cu_ai_pref_user_or_workspace",
            ),
            models.CheckConstraint(
                condition=(Q(connection__isnull=True) | Q(pool__isnull=True)),
                name="cu_ai_pref_not_conn_and_pool",
            ),
            models.UniqueConstraint(
                fields=["user", "project", "purpose"],
                condition=Q(user__isnull=False, project__isnull=False),
                name="cu_ai_pref_unique_user_project",
            ),
            models.UniqueConstraint(
                fields=["user", "purpose"],
                condition=Q(user__isnull=False, project__isnull=True),
                name="cu_ai_pref_unique_user_global",
            ),
            models.UniqueConstraint(
                fields=["project", "purpose"],
                condition=Q(user__isnull=True, project__isnull=False),
                name="cu_ai_pref_unique_workspace",
            ),
        ]


class AIProviderInvocation(models.Model):
    """Redacted audit record and pinned provider session identity."""

    STATUS_QUEUED = "queued"
    STATUS_LEASED = "leased"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_LEASED, "Leased"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_provider_invocations",
    )
    project = models.ForeignKey(
        "core_ui.Project",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_provider_invocations",
    )
    connection = models.ForeignKey(
        AIProviderConnection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invocations",
    )
    pool = models.ForeignKey(
        AIProviderPool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invocations",
    )
    target_id = models.CharField(max_length=64, choices=ALL_TARGET_CHOICES)
    purpose = models.CharField(max_length=40)
    source_kind = models.CharField(max_length=60)
    source_id = models.CharField(max_length=120)
    mode = models.CharField(max_length=20, choices=[(mode.value, mode.value) for mode in ExecutionMode])
    binding_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    provider_session_id = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=160, blank=True, default="")
    idempotency_scope = models.CharField(max_length=64, blank=True, default="")
    usage = models.JSONField(default=dict, blank=True)
    terminal_event = models.JSONField(default=dict, blank=True)
    event_log = models.JSONField(default=list, blank=True)
    event_cursor = models.PositiveBigIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_scope"],
                condition=~Q(idempotency_scope=""),
                name="cu_ai_invocation_idempotent_scope",
            )
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="cu_ai_inv_user_created"),
            models.Index(fields=["status", "created_at"], name="cu_ai_inv_status_created"),
            models.Index(fields=["source_kind", "source_id"], name="cu_ai_inv_source"),
        ]


class AIProviderLease(models.Model):
    """Fenced connection slot leased to one durable invocation."""

    STATUS_ACTIVE = "active"
    STATUS_RELEASED = "released"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_RELEASED, "Released"),
        (STATUS_EXPIRED, "Expired"),
    ]

    invocation = models.ForeignKey(AIProviderInvocation, on_delete=models.CASCADE, related_name="leases")
    connection = models.ForeignKey(AIProviderConnection, on_delete=models.CASCADE, related_name="leases")
    slot = models.PositiveSmallIntegerField(default=1)
    lease_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fencing_token = models.PositiveBigIntegerField(default=1)
    owner_id = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    acquired_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(slot__gte=1), name="cu_ai_lease_slot_gte1"),
            models.UniqueConstraint(
                fields=["invocation"],
                condition=Q(status="active"),
                name="cu_ai_lease_one_active_inv",
            ),
            models.UniqueConstraint(
                fields=["connection", "slot"],
                condition=Q(status="active"),
                name="cu_ai_lease_unique_active_slot",
            ),
        ]
        indexes = [models.Index(fields=["status", "expires_at"], name="cu_ai_lease_status_exp")]
