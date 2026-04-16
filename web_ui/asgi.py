"""
ASGI config for web_ui project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_ui.settings.development')

django_asgi_app = get_asgi_application()
http_application = (
    ASGIStaticFilesHandler(django_asgi_app)
    if getattr(settings, "SERVE_STATIC_FILES", False)
    else django_asgi_app
)

import web_ui.routing  # noqa: E402

application = ProtocolTypeRouter({
    "http": http_application,
    "websocket": AuthMiddlewareStack(
        URLRouter(web_ui.routing.websocket_urlpatterns)
    ),
})
