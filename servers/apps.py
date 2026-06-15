from django.apps import AppConfig


class ServersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "servers"

    def ready(self):
        from app.agent_kernel import ops_runtime_registry
        from servers.ops_runtime_adapter import ServersOpsRuntimeProvider

        ops_runtime_registry.register(ServersOpsRuntimeProvider())

        from . import signals  # noqa: F401
