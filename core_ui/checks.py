from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def channels_redis_deploy_check(app_configs, **kwargs):
    backend = (
        settings.CHANNEL_LAYERS.get("default", {})
        .get("BACKEND", "")
    )
    if settings.DEBUG or backend != "channels.layers.InMemoryChannelLayer":
        return []

    return [
        Error(
            "Channels uses InMemoryChannelLayer while DEBUG=False.",
            hint="Set CHANNEL_REDIS_URL and deploy Redis for cross-process WebSocket control.",
            id="core_ui.E001",
        ),
    ]
