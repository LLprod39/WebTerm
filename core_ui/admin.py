from django.contrib import admin

from .models import Project, ProjectMembership, UserActivityLog, UserAppPermission


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "is_default", "is_archived", "created_at"]
    list_filter = ["is_default", "is_archived"]
    search_fields = ["name", "slug", "owner__username"]


@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ["project", "user", "role", "is_active", "created_at"]
    list_filter = ["role", "is_active"]
    search_fields = ["project__name", "user__username", "user__email"]


@admin.register(UserAppPermission)
class UserAppPermissionAdmin(admin.ModelAdmin):
    list_display = ["user", "feature", "allowed"]
    list_filter = ["feature", "allowed"]
    search_fields = ["user__username", "user__email"]
    ordering = ["user", "feature"]
    list_editable = ["allowed"]


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "username_snapshot", "category", "action", "status", "entity_name", "ip_address"]
    list_filter = ["category", "action", "status", "created_at"]
    search_fields = ["username_snapshot", "description", "entity_name", "entity_id", "action"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]
