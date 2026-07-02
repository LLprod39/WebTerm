from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class K8sProvider(models.Model):
    KIND_RANCHER = "rancher"
    KIND_DEVTRON = "devtron"
    KIND_CHOICES = [
        (KIND_RANCHER, "Rancher"),
        (KIND_DEVTRON, "Devtron"),
    ]

    AUTH_NONE = "none"
    AUTH_SECRET_REF = "secret_ref"
    AUTH_OIDC = "oidc"
    AUTH_CHOICES = [
        (AUTH_NONE, "None"),
        (AUTH_SECRET_REF, "Secret reference"),
        (AUTH_OIDC, "OIDC"),
    ]

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    base_url = models.URLField()
    enabled = models.BooleanField(default=True)
    auth_mode = models.CharField(max_length=30, choices=AUTH_CHOICES, default=AUTH_SECRET_REF)
    secret_ref = models.CharField(max_length=200, blank=True, default="")
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "name"], name="k8s_provider_kind_name_unique"),
        ]
        indexes = [
            models.Index(fields=["kind", "enabled"], name="k8s_provider_kind_enabled_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.name}"


class K8sCluster(models.Model):
    HEALTH_HEALTHY = "healthy"
    HEALTH_WARNING = "warning"
    HEALTH_DEGRADED = "degraded"
    HEALTH_UNKNOWN = "unknown"
    HEALTH_CHOICES = [
        (HEALTH_HEALTHY, "Healthy"),
        (HEALTH_WARNING, "Warning"),
        (HEALTH_DEGRADED, "Degraded"),
        (HEALTH_UNKNOWN, "Unknown"),
    ]

    name = models.CharField(max_length=160, unique=True)
    environment = models.CharField(max_length=50, blank=True, default="")
    health = models.CharField(max_length=30, choices=HEALTH_CHOICES, default=HEALTH_UNKNOWN)
    rancher_provider = models.ForeignKey(
        K8sProvider,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rancher_clusters",
        limit_choices_to={"kind": K8sProvider.KIND_RANCHER},
    )
    rancher_cluster_id = models.CharField(max_length=160, blank=True, default="")
    devtron_cluster_id = models.CharField(max_length=160, blank=True, default="")
    nodes_ready = models.PositiveIntegerField(default=0)
    nodes_total = models.PositiveIntegerField(default=0)
    namespace_count = models.PositiveIntegerField(default=0)
    workload_count = models.PositiveIntegerField(default=0)
    labels = models.JSONField(default=dict, blank=True)
    links = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["environment", "name"]
        indexes = [
            models.Index(fields=["environment", "health"], name="k8s_cluster_env_health_idx"),
            models.Index(fields=["rancher_cluster_id"], name="k8s_cluster_rancher_id_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class K8sNamespace(models.Model):
    name = models.CharField(max_length=120)
    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE, related_name="namespaces_inventory")
    environment = models.CharField(max_length=50, blank=True, default="")
    health = models.CharField(max_length=30, choices=K8sCluster.HEALTH_CHOICES, default=K8sCluster.HEALTH_UNKNOWN)
    app_count = models.PositiveIntegerField(default=0)
    workload_count = models.PositiveIntegerField(default=0)
    labels = models.JSONField(default=dict, blank=True)
    links = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cluster__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "name"], name="k8s_namespace_cluster_name_unique"),
        ]
        indexes = [
            models.Index(fields=["health"], name="k8s_namespace_health_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.name}"


class K8sWorkloadRef(models.Model):
    KIND_DEPLOYMENT = "deployment"
    KIND_STATEFULSET = "statefulset"
    KIND_DAEMONSET = "daemonset"
    KIND_CRONJOB = "cronjob"
    KIND_JOB = "job"
    KIND_POD = "pod"
    KIND_UNKNOWN = "unknown"
    KIND_CHOICES = [
        (KIND_DEPLOYMENT, "Deployment"),
        (KIND_STATEFULSET, "StatefulSet"),
        (KIND_DAEMONSET, "DaemonSet"),
        (KIND_CRONJOB, "CronJob"),
        (KIND_JOB, "Job"),
        (KIND_POD, "Pod"),
        (KIND_UNKNOWN, "Unknown"),
    ]

    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE, related_name="workload_refs")
    namespace = models.CharField(max_length=120)
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES, default=KIND_UNKNOWN)
    environment = models.CharField(max_length=50, blank=True, default="")
    owner = models.CharField(max_length=60, blank=True, default="rancher")
    team = models.CharField(max_length=120, blank=True, default="")
    health = models.CharField(max_length=30, choices=K8sCluster.HEALTH_CHOICES, default=K8sCluster.HEALTH_UNKNOWN)
    ready = models.PositiveIntegerField(default=0)
    desired = models.PositiveIntegerField(default=0)
    version = models.CharField(max_length=120, blank=True, default="")
    links = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cluster__name", "namespace", "kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "namespace", "kind", "name"], name="k8s_workload_cluster_ns_kind_name_unique"),
        ]
        indexes = [
            models.Index(fields=["kind", "health"], name="k8s_workload_kind_health_idx"),
            models.Index(fields=["namespace"], name="k8s_workload_namespace_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.namespace}/{self.kind}/{self.name}"


class K8sAppRef(models.Model):
    OWNER_FLEET = "fleet"
    OWNER_DEVTRON = "devtron"
    OWNER_EXTERNAL = "external"
    OWNER_CHOICES = [
        (OWNER_FLEET, "Fleet"),
        (OWNER_DEVTRON, "Devtron"),
        (OWNER_EXTERNAL, "External"),
    ]

    name = models.CharField(max_length=180)
    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE, related_name="apps")
    namespace = models.CharField(max_length=120)
    environment = models.CharField(max_length=50, blank=True, default="")
    owner = models.CharField(max_length=30, choices=OWNER_CHOICES)
    team = models.CharField(max_length=120, blank=True, default="")
    health = models.CharField(max_length=30, choices=K8sCluster.HEALTH_CHOICES, default=K8sCluster.HEALTH_UNKNOWN)
    version = models.CharField(max_length=120, blank=True, default="")
    links = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cluster__name", "namespace", "name"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "namespace", "name"], name="k8s_app_cluster_ns_name_unique"),
        ]
        indexes = [
            models.Index(fields=["owner", "health"], name="k8s_app_owner_health_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.namespace}/{self.name}"


class K8sFleetBundle(models.Model):
    STATUS_READY = "ready"
    STATUS_ROLLING = "rolling"
    STATUS_DEGRADED = "degraded"
    STATUS_PAUSED = "paused"
    STATUS_UNKNOWN = "unknown"
    STATUS_CHOICES = [
        (STATUS_READY, "Ready"),
        (STATUS_ROLLING, "Rolling"),
        (STATUS_DEGRADED, "Degraded"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_UNKNOWN, "Unknown"),
    ]

    name = models.CharField(max_length=180, unique=True)
    source = models.CharField(max_length=240, blank=True, default="")
    target = models.CharField(max_length=240, blank=True, default="")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_UNKNOWN)
    ready = models.PositiveIntegerField(default=0)
    desired = models.PositiveIntegerField(default=0)
    partitions = models.JSONField(default=list, blank=True)
    links = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status"], name="k8s_fleet_bundle_status_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class K8sNetworkRef(models.Model):
    KIND_SERVICE = "service"
    KIND_INGRESS = "ingress"
    KIND_CHOICES = [
        (KIND_SERVICE, "Service"),
        (KIND_INGRESS, "Ingress"),
    ]

    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE, related_name="network_refs")
    namespace = models.CharField(max_length=120)
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    environment = models.CharField(max_length=50, blank=True, default="")
    health = models.CharField(max_length=30, choices=K8sCluster.HEALTH_CHOICES, default=K8sCluster.HEALTH_UNKNOWN)
    service_type = models.CharField(max_length=80, blank=True, default="")
    ports = models.JSONField(default=list, blank=True)
    hosts = models.JSONField(default=list, blank=True)
    endpoints = models.JSONField(default=list, blank=True)
    links = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cluster__name", "namespace", "kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "namespace", "kind", "name"], name="k8s_network_cluster_ns_kind_name_unique"),
        ]
        indexes = [
            models.Index(fields=["kind", "health"], name="k8s_network_kind_health_idx"),
            models.Index(fields=["namespace"], name="k8s_network_namespace_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.namespace}/{self.kind}/{self.name}"


class K8sPodRef(models.Model):
    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE, related_name="pod_refs")
    namespace = models.CharField(max_length=120)
    name = models.CharField(max_length=180)
    environment = models.CharField(max_length=50, blank=True, default="")
    health = models.CharField(max_length=30, choices=K8sCluster.HEALTH_CHOICES, default=K8sCluster.HEALTH_UNKNOWN)
    phase = models.CharField(max_length=80, blank=True, default="")
    node_name = models.CharField(max_length=180, blank=True, default="")
    pod_ip = models.CharField(max_length=80, blank=True, default="")
    host_ip = models.CharField(max_length=80, blank=True, default="")
    owner_kind = models.CharField(max_length=80, blank=True, default="")
    owner_name = models.CharField(max_length=180, blank=True, default="")
    ready_containers = models.PositiveIntegerField(default=0)
    total_containers = models.PositiveIntegerField(default=0)
    restart_count = models.PositiveIntegerField(default=0)
    images = models.JSONField(default=list, blank=True)
    links = models.JSONField(default=dict, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cluster__name", "namespace", "name"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "namespace", "name"], name="k8s_pod_cluster_ns_name_unique"),
        ]
        indexes = [
            models.Index(fields=["health"], name="k8s_pod_health_idx"),
            models.Index(fields=["namespace"], name="k8s_pod_namespace_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.namespace}/pod/{self.name}"


class K8sEvent(models.Model):
    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_ERROR = "error"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_ERROR, "Error"),
    ]

    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE, related_name="events")
    event_uid = models.CharField(max_length=200)
    source = models.CharField(max_length=80, default="rancher")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_INFO)
    reason = models.CharField(max_length=160, blank=True, default="")
    message = models.TextField(blank=True, default="")
    namespace = models.CharField(max_length=120, blank=True, default="")
    involved_kind = models.CharField(max_length=80, blank=True, default="")
    involved_name = models.CharField(max_length=180, blank=True, default="")
    count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    labels = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["cluster", "event_uid"], name="k8s_event_cluster_uid_unique"),
        ]
        indexes = [
            models.Index(fields=["severity", "-last_seen_at"], name="k8s_event_severity_seen_idx"),
            models.Index(fields=["namespace"], name="k8s_event_namespace_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.cluster.name}/{self.reason or self.event_uid}"


class K8sAuditEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    username_snapshot = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=120)
    provider = models.CharField(max_length=50, blank=True, default="")
    cluster = models.ForeignKey(K8sCluster, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["action", "-created_at"], name="k8s_audit_action_created_idx"),
            models.Index(fields=["user", "-created_at"], name="k8s_audit_user_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} @{self.created_at:%Y-%m-%d %H:%M:%S}"


class K8sActionRequest(models.Model):
    ACTION_K8S_ROLLOUT_RESTART = "k8s.rollout.restart"
    ACTION_K8S_WORKLOAD_SCALE = "k8s.workload.scale"
    ACTION_K8S_RESOURCE_APPLY = "k8s.resource.apply"
    ACTION_K8S_RESOURCE_PATCH = "k8s.resource.patch"
    ACTION_K8S_RESOURCE_DELETE = "k8s.resource.delete"
    ACTION_FLEET_ROLLOUT_PAUSE = "fleet.rollout.pause"
    ACTION_FLEET_ROLLOUT_RESUME = "fleet.rollout.resume"
    ACTION_GITOPS_CREATE_MERGE_REQUEST = "gitops.create_merge_request"
    ACTION_DEVTRON_OPEN_ROLLBACK = "devtron.open_rollback"
    ACTION_CHOICES = [
        (ACTION_K8S_ROLLOUT_RESTART, "Kubernetes rollout restart"),
        (ACTION_K8S_WORKLOAD_SCALE, "Kubernetes workload scale"),
        (ACTION_K8S_RESOURCE_APPLY, "Kubernetes resource apply"),
        (ACTION_K8S_RESOURCE_PATCH, "Kubernetes resource patch"),
        (ACTION_K8S_RESOURCE_DELETE, "Kubernetes resource delete"),
        (ACTION_FLEET_ROLLOUT_PAUSE, "Fleet rollout pause"),
        (ACTION_FLEET_ROLLOUT_RESUME, "Fleet rollout resume"),
        (ACTION_GITOPS_CREATE_MERGE_REQUEST, "GitOps merge request"),
        (ACTION_DEVTRON_OPEN_ROLLBACK, "Devtron rollback deep link"),
    ]

    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_APPROVED_EXTERNAL = "approved_external"
    STATUS_EXECUTED_NATIVE = "executed_native"
    STATUS_EXECUTION_BLOCKED = "execution_blocked"
    STATUS_VERIFIED_EXTERNAL = "verified_external"
    STATUS_VERIFIED_NATIVE = "verified_native"
    STATUS_VERIFICATION_FAILED = "verification_failed"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING_APPROVAL, "Pending approval"),
        (STATUS_APPROVED_EXTERNAL, "Approved for external execution"),
        (STATUS_EXECUTED_NATIVE, "Executed natively by WebTerm"),
        (STATUS_EXECUTION_BLOCKED, "Execution blocked"),
        (STATUS_VERIFIED_EXTERNAL, "Verified external execution"),
        (STATUS_VERIFIED_NATIVE, "Verified native execution"),
        (STATUS_VERIFICATION_FAILED, "Action verification failed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CHOICES = [
        (RISK_LOW, "Low"),
        (RISK_MEDIUM, "Medium"),
        (RISK_HIGH, "High"),
    ]

    request_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="kubernetes_action_requests",
    )
    username_snapshot = models.CharField(max_length=150, blank=True, default="")
    action = models.CharField(max_length=80, choices=ACTION_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_APPROVAL)
    risk_tier = models.CharField(max_length=20, choices=RISK_CHOICES, default=RISK_HIGH)
    cluster = models.ForeignKey(K8sCluster, null=True, blank=True, on_delete=models.SET_NULL)
    target = models.JSONField(default=dict, blank=True)
    preview = models.JSONField(default=dict, blank=True)
    execution_policy = models.JSONField(default=dict, blank=True)
    report = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True, default="")
    approval_ref = models.CharField(max_length=160, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="k8s_action_status_created_idx"),
            models.Index(fields=["action", "-created_at"], name="k8s_action_action_created_idx"),
            models.Index(fields=["request_id"], name="k8s_action_reqid_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.request_id}"


from kubernetes_ops.admin_models import K8sAdminAction, K8sAdminRecording, K8sAdminRecordingEvent, K8sAdminSession  # noqa: E402,F401
