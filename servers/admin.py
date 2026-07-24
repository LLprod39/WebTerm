from django.contrib import admin

from .models import (
    AgentRun,
    AgentRunArtifact,
    Playbook,
    PlaybookAssetBundle,
    PlaybookAuditEvent,
    PlaybookBindingProfile,
    PlaybookCompatibilityRevision,
    PlaybookDraft,
    PlaybookGrant,
    PlaybookRevision,
    PlaybookRun,
    PlaybookRunDispatch,
    PlaybookValidation,
    Server,
    ServerAgent,
    ServerAlert,
    ServerCommandHistory,
    ServerConnection,
    ServerGroup,
    ServerGroupMember,
    ServerGroupPermission,
    ServerGroupSubscription,
    ServerGroupTag,
    ServerHealthCheck,
)


@admin.register(ServerGroup)
class ServerGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name"]


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "host",
        "port",
        "username",
        "auth_method",
        "sudo_auth_mode",
        "user",
        "is_active",
        "ai_read_only",
        "created_at",
    ]
    list_filter = ["auth_method", "sudo_auth_mode", "is_active", "ai_read_only", "created_at"]
    search_fields = ["name", "host", "username"]
    readonly_fields = ["created_at", "updated_at", "last_connected"]


@admin.register(ServerConnection)
class ServerConnectionAdmin(admin.ModelAdmin):
    list_display = ["server", "user", "status", "connected_at", "last_seen_at", "disconnected_at"]
    list_filter = ["status", "connected_at", "last_seen_at"]
    readonly_fields = ["connected_at", "last_seen_at", "disconnected_at"]


@admin.register(ServerCommandHistory)
class ServerCommandHistoryAdmin(admin.ModelAdmin):
    list_display = ["server", "user", "command", "exit_code", "executed_at"]
    list_filter = ["executed_at", "exit_code"]
    readonly_fields = ["executed_at"]
    search_fields = ["command", "server__name"]


@admin.register(ServerGroupTag)
class ServerGroupTagAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "created_at"]
    search_fields = ["name"]


@admin.register(ServerGroupMember)
class ServerGroupMemberAdmin(admin.ModelAdmin):
    list_display = ["group", "user", "role", "joined_at"]
    list_filter = ["role"]
    search_fields = ["group__name", "user__username"]


@admin.register(ServerGroupSubscription)
class ServerGroupSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["group", "user", "kind", "created_at"]
    list_filter = ["kind"]


@admin.register(ServerGroupPermission)
class ServerGroupPermissionAdmin(admin.ModelAdmin):
    list_display = ["group", "user", "can_view", "can_execute", "can_edit", "can_manage_members"]


@admin.register(ServerHealthCheck)
class ServerHealthCheckAdmin(admin.ModelAdmin):
    list_display = [
        "server",
        "status",
        "cpu_percent",
        "memory_percent",
        "disk_percent",
        "response_time_ms",
        "checked_at",
    ]
    list_filter = ["status", "is_deep", "checked_at"]
    readonly_fields = ["checked_at"]
    search_fields = ["server__name", "server__host"]


@admin.register(ServerAlert)
class ServerAlertAdmin(admin.ModelAdmin):
    list_display = ["server", "alert_type", "severity", "title", "is_resolved", "created_at"]
    list_filter = ["severity", "alert_type", "is_resolved", "created_at"]
    readonly_fields = ["created_at", "resolved_at"]
    search_fields = ["server__name", "title", "message"]


@admin.register(ServerAgent)
class ServerAgentAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "agent_type", "is_enabled", "schedule_minutes", "last_run_at"]
    list_filter = ["agent_type", "is_enabled"]
    search_fields = ["name", "user__username"]
    readonly_fields = ["created_at", "updated_at", "last_run_at"]


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ["agent", "server", "user", "status", "duration_ms", "started_at"]
    list_filter = ["status", "started_at"]
    readonly_fields = ["started_at", "completed_at"]
    search_fields = ["agent__name", "server__name"]


@admin.register(AgentRunArtifact)
class AgentRunArtifactAdmin(admin.ModelAdmin):
    list_display = ["name", "run", "user", "artifact_type", "size_bytes", "created_at"]
    list_filter = ["artifact_type", "created_at"]
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["name", "run__agent__name", "user__username"]


@admin.register(Playbook)
class PlaybookAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "kind", "category", "visibility", "last_run_status", "updated_at"]
    list_filter = ["kind", "category", "visibility"]
    search_fields = ["name", "description", "user__username"]
    readonly_fields = ["created_at", "updated_at", "last_run_at"]


@admin.register(PlaybookRun)
class PlaybookRunAdmin(admin.ModelAdmin):
    list_display = ["id", "playbook", "user", "status", "started_at", "finished_at", "created_at"]
    list_filter = ["status", "created_at"]
    readonly_fields = ["created_at", "started_at", "finished_at"]
    search_fields = ["playbook__name", "user__username"]


@admin.register(PlaybookCompatibilityRevision)
class PlaybookCompatibilityRevisionAdmin(admin.ModelAdmin):
    list_display = ["id", "playbook", "user", "status", "created_at"]
    list_filter = ["status", "created_at"]
    readonly_fields = ["created_at"]
    search_fields = ["playbook__name", "user__username", "source_hash"]


@admin.register(PlaybookRevision)
class PlaybookRevisionAdmin(admin.ModelAdmin):
    list_display = ["playbook", "revision_number", "content_format", "origin_type", "author", "created_at"]
    list_filter = ["content_format", "origin_type", "created_at"]
    search_fields = ["playbook__name", "content_hash", "author__username"]
    readonly_fields = [field.name for field in PlaybookRevision._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlaybookDraft)
class PlaybookDraftAdmin(admin.ModelAdmin):
    list_display = ["playbook", "base_revision", "version", "last_editor", "updated_at"]
    search_fields = ["playbook__name", "last_editor__username", "content_hash"]
    readonly_fields = [field.name for field in PlaybookDraft._meta.fields]


@admin.register(PlaybookValidation)
class PlaybookValidationAdmin(admin.ModelAdmin):
    list_display = ["revision", "status", "binding_profile", "requested_by", "started_at", "finished_at"]
    list_filter = ["status", "started_at"]
    search_fields = ["revision__playbook__name", "runtime_fingerprint_hash", "target_signature"]
    readonly_fields = [field.name for field in PlaybookValidation._meta.fields]


@admin.register(PlaybookBindingProfile)
class PlaybookBindingProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "playbook", "user", "is_default", "version", "updated_at"]
    search_fields = ["name", "playbook__name", "user__username"]
    readonly_fields = ["content_hash", "version", "created_at", "updated_at"]


@admin.register(PlaybookGrant)
class PlaybookGrantAdmin(admin.ModelAdmin):
    list_display = ["playbook", "principal_label", "role", "is_legacy", "expires_at", "revoked_at"]
    list_filter = ["role", "workspace_shared", "is_legacy", "revoked_at"]
    search_fields = ["playbook__name", "user__username", "group__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(PlaybookAssetBundle)
class PlaybookAssetBundleAdmin(admin.ModelAdmin):
    list_display = ["id", "content_hash", "file_count", "size_bytes", "scan_status", "created_by", "created_at"]
    list_filter = ["scan_status", "created_at"]
    search_fields = ["content_hash", "storage_key"]
    readonly_fields = [field.name for field in PlaybookAssetBundle._meta.fields]


@admin.register(PlaybookRunDispatch)
class PlaybookRunDispatchAdmin(admin.ModelAdmin):
    list_display = ["run", "status", "claimed_by", "attempt_count", "queued_at", "lease_expires_at"]
    list_filter = ["status", "queued_at"]
    search_fields = ["run__playbook__name", "claimed_by", "error"]
    readonly_fields = [field.name for field in PlaybookRunDispatch._meta.fields]


@admin.register(PlaybookAuditEvent)
class PlaybookAuditEventAdmin(admin.ModelAdmin):
    list_display = ["playbook", "event_type", "actor", "entity_type", "entity_id", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["playbook__name", "actor__username", "entity_id"]
    readonly_fields = [field.name for field in PlaybookAuditEvent._meta.fields]
