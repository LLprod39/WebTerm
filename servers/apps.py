from django.apps import AppConfig


class ServersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "servers"

    def ready(self) -> None:
        from servers.app_registration_agents import register_agent_adapters
        from servers.app_registration_platform import register_platform_adapters
        from servers.app_registration_security import register_security_adapters

        register_agent_adapters()
        register_platform_adapters()
        register_security_adapters()

        from . import (
            checks,  # noqa: F401
            lifecycle_memory_events,  # noqa: F401
            signals,  # noqa: F401
        )
