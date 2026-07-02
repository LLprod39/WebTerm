from django.contrib import admin

from kubernetes_ops.models import (
    K8sActionRequest,
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sAdminSession,
    K8sAppRef,
    K8sAuditEvent,
    K8sCluster,
    K8sEvent,
    K8sFleetBundle,
    K8sNamespace,
    K8sNetworkRef,
    K8sPodRef,
    K8sProvider,
    K8sWorkloadRef,
)


@admin.register(K8sProvider)
class K8sProviderAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "base_url", "enabled", "auth_mode", "last_sync_at", "updated_at"]
    list_filter = ["kind", "enabled", "auth_mode"]
    search_fields = ["name", "base_url"]
    readonly_fields = ["created_at", "updated_at", "last_sync_at"]


@admin.register(K8sCluster)
class K8sClusterAdmin(admin.ModelAdmin):
    list_display = ["name", "environment", "health", "nodes_ready", "nodes_total", "last_sync_at"]
    list_filter = ["environment", "health"]
    search_fields = ["name", "rancher_cluster_id", "devtron_cluster_id"]


@admin.register(K8sAppRef)
class K8sAppRefAdmin(admin.ModelAdmin):
    list_display = ["name", "cluster", "namespace", "owner", "team", "health", "version", "last_sync_at"]
    list_filter = ["owner", "health", "environment"]
    search_fields = ["name", "namespace", "team", "cluster__name"]


@admin.register(K8sNamespace)
class K8sNamespaceAdmin(admin.ModelAdmin):
    list_display = ["name", "cluster", "environment", "health", "app_count", "workload_count", "last_sync_at"]
    list_filter = ["health", "environment"]
    search_fields = ["name", "cluster__name"]


@admin.register(K8sWorkloadRef)
class K8sWorkloadRefAdmin(admin.ModelAdmin):
    list_display = ["name", "cluster", "namespace", "kind", "health", "ready", "desired", "last_sync_at"]
    list_filter = ["kind", "health", "environment"]
    search_fields = ["name", "namespace", "team", "cluster__name"]


@admin.register(K8sFleetBundle)
class K8sFleetBundleAdmin(admin.ModelAdmin):
    list_display = ["name", "source", "target", "status", "ready", "desired", "last_sync_at"]
    list_filter = ["status"]
    search_fields = ["name", "source", "target"]


@admin.register(K8sNetworkRef)
class K8sNetworkRefAdmin(admin.ModelAdmin):
    list_display = ["name", "cluster", "namespace", "kind", "service_type", "health", "last_sync_at"]
    list_filter = ["kind", "health", "environment"]
    search_fields = ["name", "namespace", "cluster__name"]


@admin.register(K8sPodRef)
class K8sPodRefAdmin(admin.ModelAdmin):
    list_display = ["name", "cluster", "namespace", "phase", "health", "ready_containers", "total_containers", "restart_count", "last_sync_at"]
    list_filter = ["health", "phase", "environment"]
    search_fields = ["name", "namespace", "node_name", "owner_name", "cluster__name"]


@admin.register(K8sEvent)
class K8sEventAdmin(admin.ModelAdmin):
    list_display = ["reason", "cluster", "namespace", "severity", "involved_kind", "involved_name", "last_seen_at"]
    list_filter = ["severity", "source", "namespace"]
    search_fields = ["reason", "message", "namespace", "involved_name", "cluster__name"]


@admin.register(K8sAuditEvent)
class K8sAuditEventAdmin(admin.ModelAdmin):
    list_display = ["action", "username_snapshot", "provider", "cluster", "created_at"]
    list_filter = ["action", "provider", "created_at"]
    search_fields = ["action", "username_snapshot", "provider", "cluster__name"]
    readonly_fields = ["created_at"]


@admin.register(K8sActionRequest)
class K8sActionRequestAdmin(admin.ModelAdmin):
    list_display = ["request_id", "action", "status", "risk_tier", "username_snapshot", "cluster", "created_at"]
    list_filter = ["action", "status", "risk_tier", "created_at"]
    search_fields = ["request_id", "action", "username_snapshot", "cluster__name", "reason"]
    readonly_fields = ["request_id", "created_at", "updated_at"]


@admin.register(K8sAdminSession)
class K8sAdminSessionAdmin(admin.ModelAdmin):
    list_display = ["session_id", "mode", "status", "risk_tier", "username_snapshot", "cluster", "namespace", "expires_at"]
    list_filter = ["mode", "status", "risk_tier", "created_at"]
    search_fields = ["session_id", "username_snapshot", "cluster__name", "namespace", "reason", "approval_ref"]
    readonly_fields = ["session_id", "created_at", "updated_at", "approved_at", "closed_at"]


@admin.register(K8sAdminAction)
class K8sAdminActionAdmin(admin.ModelAdmin):
    list_display = ["action_id", "verb", "status", "username_snapshot", "cluster", "namespace", "resource_kind", "resource_name"]
    list_filter = ["verb", "status", "created_at"]
    search_fields = ["action_id", "username_snapshot", "cluster__name", "namespace", "resource_api_version", "resource_kind", "resource_name"]
    readonly_fields = ["action_id", "created_at", "updated_at"]


@admin.register(K8sAdminRecording)
class K8sAdminRecordingAdmin(admin.ModelAdmin):
    list_display = ["recording_id", "operation", "status", "username_snapshot", "cluster", "namespace", "resource_kind", "resource_name"]
    list_filter = ["operation", "status", "created_at"]
    search_fields = ["recording_id", "username_snapshot", "cluster__name", "namespace", "resource_kind", "resource_name"]
    readonly_fields = ["recording_id", "created_at", "updated_at", "started_at", "finished_at"]


@admin.register(K8sAdminRecordingEvent)
class K8sAdminRecordingEventAdmin(admin.ModelAdmin):
    list_display = ["recording", "sequence", "stream", "stored_length", "redacted", "truncated", "created_at"]
    list_filter = ["stream", "redacted", "truncated", "created_at"]
    search_fields = ["recording__recording_id", "data"]
    readonly_fields = ["created_at"]
