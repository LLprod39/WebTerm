from django.contrib import admin

from plugin_marketplace.models import (
    MarketplaceCatalogItem,
    MarketplaceSource,
    PluginCompatibilityJob,
    PluginInstallation,
    PluginInstallEvent,
    PluginPackage,
    PluginPermissionGrant,
    PluginSecretBinding,
)


@admin.register(PluginPackage)
class PluginPackageAdmin(admin.ModelAdmin):
    list_display = ("plugin_id", "version", "source", "review_status", "signature_status", "updated_at")
    list_filter = ("source", "review_status", "signature_status")
    search_fields = ("plugin_id", "name", "publisher_name")


@admin.register(PluginInstallation)
class PluginInstallationAdmin(admin.ModelAdmin):
    list_display = ("plugin_id", "status", "scope_summary", "package", "installed_by", "installed_at")
    list_filter = ("status",)
    search_fields = ("plugin_id", "package__name")
    filter_horizontal = ("scoped_groups",)

    def scope_summary(self, obj: PluginInstallation) -> str:
        count = obj.scoped_groups.count()
        return "global" if count == 0 else f"{count} group(s)"


@admin.register(PluginPermissionGrant)
class PluginPermissionGrantAdmin(admin.ModelAdmin):
    list_display = ("installation", "scope", "risk_tier", "granted", "updated_at")
    list_filter = ("granted", "risk_tier")
    search_fields = ("scope", "installation__plugin_id")


@admin.register(PluginInstallEvent)
class PluginInstallEventAdmin(admin.ModelAdmin):
    list_display = ("plugin_id", "event_type", "status", "actor", "created_at")
    list_filter = ("event_type", "status")
    search_fields = ("plugin_id", "message")


@admin.register(MarketplaceCatalogItem)
class MarketplaceCatalogItemAdmin(admin.ModelAdmin):
    list_display = ("plugin_id", "version", "source", "review_status", "signature_status", "updated_at")
    list_filter = ("review_status", "signature_status")
    search_fields = ("plugin_id", "source__name")


@admin.register(PluginCompatibilityJob)
class PluginCompatibilityJobAdmin(admin.ModelAdmin):
    list_display = ("plugin_id", "version", "status", "isolation_mode", "created_at")
    list_filter = ("status", "isolation_mode")
    search_fields = ("plugin_id", "version")


admin.site.register(MarketplaceSource)
admin.site.register(PluginSecretBinding)
