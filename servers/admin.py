from django.contrib import admin

from .models import (
    AgentRun,
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
    list_display = ['name', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name']


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ['name', 'host', 'port', 'username', 'auth_method', 'user', 'is_active', 'ai_read_only', 'created_at']
    list_filter = ['auth_method', 'is_active', 'ai_read_only', 'created_at']
    search_fields = ['name', 'host', 'username']
    readonly_fields = ['created_at', 'updated_at', 'last_connected']


@admin.register(ServerConnection)
class ServerConnectionAdmin(admin.ModelAdmin):
    list_display = ['server', 'user', 'status', 'connected_at', 'last_seen_at', 'disconnected_at']
    list_filter = ['status', 'connected_at', 'last_seen_at']
    readonly_fields = ['connected_at', 'last_seen_at', 'disconnected_at']


@admin.register(ServerCommandHistory)
class ServerCommandHistoryAdmin(admin.ModelAdmin):
    list_display = ['server', 'user', 'command', 'exit_code', 'executed_at']
    list_filter = ['executed_at', 'exit_code']
    readonly_fields = ['executed_at']
    search_fields = ['command', 'server__name']


@admin.register(ServerGroupTag)
class ServerGroupTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at']
    search_fields = ['name']


@admin.register(ServerGroupMember)
class ServerGroupMemberAdmin(admin.ModelAdmin):
    list_display = ['group', 'user', 'role', 'joined_at']
    list_filter = ['role']
    search_fields = ['group__name', 'user__username']


@admin.register(ServerGroupSubscription)
class ServerGroupSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['group', 'user', 'kind', 'created_at']
    list_filter = ['kind']


@admin.register(ServerGroupPermission)
class ServerGroupPermissionAdmin(admin.ModelAdmin):
    list_display = ['group', 'user', 'can_view', 'can_execute', 'can_edit', 'can_manage_members']


@admin.register(ServerHealthCheck)
class ServerHealthCheckAdmin(admin.ModelAdmin):
    list_display = ['server', 'status', 'cpu_percent', 'memory_percent', 'disk_percent', 'response_time_ms', 'checked_at']
    list_filter = ['status', 'is_deep', 'checked_at']
    readonly_fields = ['checked_at']
    search_fields = ['server__name', 'server__host']


@admin.register(ServerAlert)
class ServerAlertAdmin(admin.ModelAdmin):
    list_display = ['server', 'alert_type', 'severity', 'title', 'is_resolved', 'created_at']
    list_filter = ['severity', 'alert_type', 'is_resolved', 'created_at']
    readonly_fields = ['created_at', 'resolved_at']
    search_fields = ['server__name', 'title', 'message']


@admin.register(ServerAgent)
class ServerAgentAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'agent_type', 'is_enabled', 'schedule_minutes', 'last_run_at']
    list_filter = ['agent_type', 'is_enabled']
    search_fields = ['name', 'user__username']
    readonly_fields = ['created_at', 'updated_at', 'last_run_at']


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ['agent', 'server', 'user', 'status', 'duration_ms', 'started_at']
    list_filter = ['status', 'started_at']
    readonly_fields = ['started_at', 'completed_at']
    search_fields = ['agent__name', 'server__name']
