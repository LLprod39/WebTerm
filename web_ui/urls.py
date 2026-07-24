"""
URL configuration for web_ui project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from plugin_marketplace.release_profile import plugin_marketplace_enabled
from web_ui.views import settings_readiness_views

admin.site.site_header = "WebTerm Admin"
admin.site.site_title = "WebTerm — Админка"
admin.site.index_title = "Управление"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/settings/readiness/", settings_readiness_views.api_settings_readiness, name="api_settings_readiness"),
    path("", include("core_ui.urls")),
    path("servers/", include("servers.urls")),
    path("api/studio/", include("studio.urls")),
    path("api/mars/", include("mars.urls")),
    path("api/kubernetes/", include("kubernetes_ops.urls")),
]

# A disabled release profile has no plugin API surface at all.  This blocks
# read and mutation endpoints even if an old database still contains enabled
# PluginInstallation rows.
if plugin_marketplace_enabled():
    urlpatterns.append(path("api/plugins/", include("plugin_marketplace.urls")))

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
