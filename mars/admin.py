from django.contrib import admin

from mars.models import MarsRun, MarsRunEvent, MarsSession, MarsWorkspace


@admin.register(MarsWorkspace)
class MarsWorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "root_path", "enabled", "updated_at")
    list_filter = ("enabled",)
    search_fields = ("name", "root_path", "user__username")


@admin.register(MarsSession)
class MarsSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "workspace", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("task_brief", "user__username", "workspace__name")


@admin.register(MarsRun)
class MarsRunAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "workspace", "status", "allow_dirty", "created_at", "completed_at")
    list_filter = ("status", "allow_dirty")
    search_fields = ("user__username", "workspace__name", "final_report")


@admin.register(MarsRunEvent)
class MarsRunEventAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "event_type", "created_at")
    list_filter = ("event_type",)
    search_fields = ("message", "event_type")
