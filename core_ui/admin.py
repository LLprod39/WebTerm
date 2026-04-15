from django.contrib import admin

from .models import UserActivityLog, UserAppPermission


@admin.register(UserAppPermission)
class UserAppPermissionAdmin(admin.ModelAdmin):
    list_display = ['user', 'feature', 'allowed']
    list_filter = ['feature', 'allowed']
    search_fields = ['user__username', 'user__email']
    ordering = ['user', 'feature']
    list_editable = ['allowed']


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'username_snapshot', 'category', 'action', 'status', 'entity_name', 'ip_address']
    list_filter = ['category', 'action', 'status', 'created_at']
    search_fields = ['username_snapshot', 'description', 'entity_name', 'entity_id', 'action']
    ordering = ['-created_at']
    readonly_fields = ['created_at']
