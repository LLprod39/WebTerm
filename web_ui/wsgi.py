"""
WSGI config for web_ui project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Deployments must set DJANGO_SETTINGS_MODULE=web_ui.settings.production explicitly
# (docker-compose / render.yaml do). Fallback mirrors asgi.py for local runs.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_ui.settings.development')

application = get_wsgi_application()
