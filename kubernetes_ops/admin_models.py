from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from kubernetes_ops.models import K8sCluster, K8sProvider


class K8sAdminSession(models.Model):
    MODE_READ = "read"
    MODE_WRITE = "write"
    MODE_BREAK_GLASS = "break_glass"
    MODE_CHOICES = [
        (MODE_READ, "Read"),
        (MODE_WRITE, "Write"),
        (MODE_BREAK_GLASS, "Break glass"),
    ]

    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_PENDING_APPROVAL, "Pending approval"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REVOKED, "Revoked"),
        (STATUS_CLOSED, "Closed"),
    ]

    RISK_LOW = "low"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"
    RISK_CHOICES = [
        (RISK_LOW, "Low"),
        (RISK_HIGH, "High"),
        (RISK_CRITICAL, "Critical"),
    ]

    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kubernetes_admin_sessions",
    )
    username_snapshot = models.CharField(max_length=150, blank=True, default="")
    provider = models.ForeignKey(K8sProvider, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_sessions")
    cluster = models.ForeignKey(K8sCluster, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_sessions")
    namespace = models.CharField(max_length=120, blank=True, default="")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_READ)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_APPROVAL)
    risk_tier = models.CharField(max_length=20, choices=RISK_CHOICES, default=RISK_HIGH)
    reason = models.TextField(blank=True, default="")
    approval_ref = models.CharField(max_length=160, blank=True, default="")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_kubernetes_admin_sessions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    allowed_verbs = models.JSONField(default=list, blank=True)
    allowed_kinds = models.JSONField(default=list, blank=True)
    allowed_namespaces = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "expires_at"], name="k8s_admin_s_status_exp_idx"),
            models.Index(fields=["user", "status"], name="k8s_admin_s_user_status_idx"),
            models.Index(fields=["mode", "status"], name="k8s_admin_s_mode_status_idx"),
            models.Index(fields=["cluster", "namespace"], name="k8s_admin_s_cluster_ns_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.mode} {self.session_id} [{self.status}]"


class K8sAdminAction(models.Model):
    VERB_GET = "get"
    VERB_LIST = "list"
    VERB_WATCH = "watch"
    VERB_LOGS = "logs"
    VERB_YAML = "yaml"
    VERB_DRY_RUN_APPLY = "dry_run_apply"
    VERB_APPLY = "apply"
    VERB_PATCH = "patch"
    VERB_SCALE = "scale"
    VERB_RESTART = "restart"
    VERB_DELETE = "delete"
    VERB_CORDON = "cordon"
    VERB_UNCORDON = "uncordon"
    VERB_DRAIN = "drain"
    VERB_EXEC = "exec"
    VERB_PORT_FORWARD = "port_forward"
    VERB_CLUSTER_TERMINAL = "cluster_terminal"
    VERB_NODE_DEBUG = "node_debug"
    VERB_CHOICES = [
        (VERB_GET, "Get"),
        (VERB_LIST, "List"),
        (VERB_WATCH, "Watch"),
        (VERB_LOGS, "Logs"),
        (VERB_YAML, "YAML"),
        (VERB_DRY_RUN_APPLY, "Dry-run apply"),
        (VERB_APPLY, "Apply"),
        (VERB_PATCH, "Patch"),
        (VERB_SCALE, "Scale"),
        (VERB_RESTART, "Restart"),
        (VERB_DELETE, "Delete"),
        (VERB_CORDON, "Cordon"),
        (VERB_UNCORDON, "Uncordon"),
        (VERB_DRAIN, "Drain"),
        (VERB_EXEC, "Exec"),
        (VERB_PORT_FORWARD, "Port forward"),
        (VERB_CLUSTER_TERMINAL, "Cluster terminal"),
        (VERB_NODE_DEBUG, "Node debug"),
    ]

    STATUS_PLANNED = "planned"
    STATUS_DRY_RUN = "dry_run"
    STATUS_EXECUTION_BLOCKED = "execution_blocked"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planned"),
        (STATUS_DRY_RUN, "Dry run"),
        (STATUS_EXECUTION_BLOCKED, "Execution blocked"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    action_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(K8sAdminSession, on_delete=models.CASCADE, related_name="actions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kubernetes_admin_actions",
    )
    username_snapshot = models.CharField(max_length=150, blank=True, default="")
    cluster = models.ForeignKey(K8sCluster, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_actions")
    namespace = models.CharField(max_length=120, blank=True, default="")
    resource_api_version = models.CharField(max_length=80, blank=True, default="")
    resource_kind = models.CharField(max_length=80, blank=True, default="")
    resource_name = models.CharField(max_length=180, blank=True, default="")
    verb = models.CharField(max_length=30, choices=VERB_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PLANNED)
    request_payload_sanitized = models.JSONField(default=dict, blank=True)
    diff_summary = models.JSONField(default=dict, blank=True)
    response_summary = models.JSONField(default=dict, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="k8s_admin_a_session_idx"),
            models.Index(fields=["verb", "status"], name="k8s_admin_a_verb_status_idx"),
            models.Index(fields=["cluster", "namespace"], name="k8s_admin_a_cluster_ns_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.verb} {self.action_id} [{self.status}]"


class K8sAdminRecording(models.Model):
    OP_EXEC = K8sAdminAction.VERB_EXEC
    OP_PORT_FORWARD = K8sAdminAction.VERB_PORT_FORWARD
    OP_CLUSTER_TERMINAL = K8sAdminAction.VERB_CLUSTER_TERMINAL
    OP_NODE_DEBUG = K8sAdminAction.VERB_NODE_DEBUG
    OPERATION_CHOICES = [
        (OP_EXEC, "Exec"),
        (OP_PORT_FORWARD, "Port forward"),
        (OP_CLUSTER_TERMINAL, "Cluster terminal"),
        (OP_NODE_DEBUG, "Node debug"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_BLOCKED = "blocked"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    recording_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(K8sAdminSession, on_delete=models.CASCADE, related_name="recordings")
    action = models.ForeignKey(
        K8sAdminAction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recordings",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kubernetes_admin_recordings",
    )
    username_snapshot = models.CharField(max_length=150, blank=True, default="")
    cluster = models.ForeignKey(K8sCluster, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_recordings")
    namespace = models.CharField(max_length=120, blank=True, default="")
    resource_kind = models.CharField(max_length=80, blank=True, default="")
    resource_name = models.CharField(max_length=180, blank=True, default="")
    operation = models.CharField(max_length=30, choices=OPERATION_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    mode = models.CharField(max_length=40, blank=True, default="metadata_only")
    transcript_required = models.BooleanField(default=False)
    transcript_stored = models.BooleanField(default=False)
    payload_stored = models.BooleanField(default=False)
    stdin_recording_required = models.BooleanField(default=False)
    stdout_recording_required = models.BooleanField(default=False)
    metadata_retention_days = models.PositiveIntegerField(default=365)
    transcript_retention_days = models.PositiveIntegerField(default=30)
    metadata_delete_after = models.DateTimeField(null=True, blank=True)
    transcript_delete_after = models.DateTimeField(null=True, blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["session", "-created_at"], name="k8s_admin_r_session_idx"),
            models.Index(fields=["action", "operation"], name="k8s_admin_r_action_op_idx"),
            models.Index(fields=["operation", "status"], name="k8s_admin_r_op_status_idx"),
            models.Index(fields=["metadata_delete_after"], name="k8s_admin_r_meta_del_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.operation} recording {self.recording_id} [{self.status}]"


class K8sAdminRecordingEvent(models.Model):
    STREAM_STDIN = "stdin"
    STREAM_STDOUT = "stdout"
    STREAM_STDERR = "stderr"
    STREAM_STATUS = "status"
    STREAM_CHOICES = [
        (STREAM_STDIN, "stdin"),
        (STREAM_STDOUT, "stdout"),
        (STREAM_STDERR, "stderr"),
        (STREAM_STATUS, "status"),
    ]

    recording = models.ForeignKey(K8sAdminRecording, on_delete=models.CASCADE, related_name="events")
    sequence = models.PositiveIntegerField(default=0)
    stream = models.CharField(max_length=20, choices=STREAM_CHOICES)
    data = models.TextField(blank=True, default="")
    original_length = models.PositiveIntegerField(default=0)
    stored_length = models.PositiveIntegerField(default=0)
    redacted = models.BooleanField(default=False)
    truncated = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["recording", "sequence", "id"]
        indexes = [
            models.Index(fields=["recording", "sequence"], name="k8s_admin_re_rec_seq_idx"),
            models.Index(fields=["stream", "created_at"], name="k8s_admin_re_stream_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.stream} event {self.sequence} for {self.recording_id}"
