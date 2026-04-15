from django.apps import AppConfig


class CoreUiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core_ui'

    def ready(self):
        from django.db.backends.signals import connection_created

        import core_ui.checks  # noqa: F401
        import core_ui.logging_setup  # noqa: F401
        import core_ui.signals  # noqa: F401

        core_ui.logging_setup.configure_loguru_sinks()

        def _sqlite_wal_mode(sender, connection, **kwargs):
            if connection.vendor == "sqlite":
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA journal_mode=WAL")

        connection_created.connect(_sqlite_wal_mode)
