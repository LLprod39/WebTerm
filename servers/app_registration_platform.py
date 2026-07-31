"""Register monitoring and platform adapters owned by the servers application."""


def register_platform_adapters() -> None:
    from app.admin_metrics_provider import register_admin_server_metrics_provider
    from app.monitoring_retention_provider import register_monitoring_retention_provider
    from app.prometheus_registry import register_prometheus_provider
    from app.server_alert_provider import register_server_alert_provider
    from app.smoke_seed_provider import register_smoke_server_seed_provider
    from app.studio_server_access import register_studio_server_access_provider
    from servers.admin_metrics_provider import DjangoAdminServerMetricsProvider
    from servers.assistant_actions import register_assistant_actions
    from servers.monitoring.metrics_rollup import cleanup_metric_data
    from servers.prometheus_metrics import server_prometheus_lines
    from servers.server_alert_provider import DjangoServerAlertProvider
    from servers.smoke_seed_provider import DjangoSmokeServerSeedProvider
    from servers.studio_server_access_provider import DjangoStudioServerAccessProvider

    register_admin_server_metrics_provider(DjangoAdminServerMetricsProvider())
    register_monitoring_retention_provider(cleanup_metric_data)
    register_prometheus_provider("servers", server_prometheus_lines)
    register_server_alert_provider(DjangoServerAlertProvider())
    register_smoke_server_seed_provider(DjangoSmokeServerSeedProvider())
    register_studio_server_access_provider(DjangoStudioServerAccessProvider())
    register_assistant_actions()
