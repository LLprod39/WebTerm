from __future__ import annotations

from django.apps import AppConfig


class PluginMarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "plugin_marketplace"
    verbose_name = "Plugin Extensions"

    def ready(self) -> None:
        import plugin_marketplace.checks  # noqa: F401
        from plugin_marketplace.release_profile import plugin_marketplace_enabled

        # In the v0.1 production profile, do not register installed manifests,
        # execution providers, tools, hooks, or Studio nodes.  URL routing is
        # independently excluded in web_ui.urls for defence in depth.
        if not plugin_marketplace_enabled():
            return

        from app.plugins.agent_tools import (
            register_enabled_plugin_ids_provider as register_agent_tool_enabled_provider,
        )
        from app.plugins.agent_tools import (
            register_plugin_agent_tool_execution_provider,
        )
        from app.plugins.catalog import ensure_builtin_plugins_registered, register_installed_plugin_manifest_provider
        from app.plugins.hooks import (
            register_enabled_plugin_ids_provider as register_hook_enabled_provider,
        )
        from app.plugins.hooks import (
            register_plugin_hook_execution_provider,
        )
        from app.plugins.permissions import register_permission_provider
        from app.plugins.studio_nodes import (
            register_enabled_plugin_ids_provider,
            register_plugin_node_execution_provider,
        )
        from app.plugins.terminal_actions import (
            register_enabled_plugin_ids_provider as register_terminal_action_enabled_provider,
        )
        from app.plugins.terminal_actions import (
            register_plugin_terminal_action_execution_provider,
        )
        from plugin_marketplace.services.agent_tool_service import (
            agent_tool_execution_provider,
            terminal_action_execution_provider,
        )
        from plugin_marketplace.services.hook_service import plugin_hook_execution_provider
        from plugin_marketplace.services.install_service import enabled_installed_plugin_manifests, enabled_plugin_ids
        from plugin_marketplace.services.permission_service import permission_provider
        from plugin_marketplace.services.studio_node_service import studio_node_execution_provider

        ensure_builtin_plugins_registered()
        register_installed_plugin_manifest_provider(enabled_installed_plugin_manifests)
        register_permission_provider(permission_provider)
        register_enabled_plugin_ids_provider(enabled_plugin_ids)
        register_plugin_node_execution_provider(studio_node_execution_provider)
        register_agent_tool_enabled_provider(enabled_plugin_ids)
        register_plugin_agent_tool_execution_provider(agent_tool_execution_provider)
        register_terminal_action_enabled_provider(enabled_plugin_ids)
        register_plugin_terminal_action_execution_provider(terminal_action_execution_provider)
        register_hook_enabled_provider(enabled_plugin_ids)
        register_plugin_hook_execution_provider(plugin_hook_execution_provider)
