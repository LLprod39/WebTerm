from django.apps import AppConfig


class ServersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "servers"

    def ready(self):
        import servers.signals  # noqa: F401
