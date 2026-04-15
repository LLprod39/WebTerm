from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.auth_login),
    path("auth/refresh/", views.auth_refresh),
    path("auth/logout/", views.auth_logout),
    path("auth/me/", views.auth_me),
    path("bootstrap/", views.bootstrap),
    path("terminal/ws-ticket/", views.terminal_ws_ticket),
    path("servers/", views.servers_collection),
    path("servers/groups/", views.server_groups),
    path("servers/context/global/", views.global_context),
    path("servers/context/groups/<int:group_id>/", views.group_context),
    path("servers/<int:server_id>/", views.server_detail),
    path("servers/<int:server_id>/knowledge/", views.server_knowledge_collection),
    path("servers/<int:server_id>/knowledge/<int:knowledge_id>/", views.server_knowledge_detail),
    path("mcp/", views.mcp_collection),
    path("mcp/<int:mcp_id>/", views.mcp_detail),
    path("mcp/<int:mcp_id>/test/", views.mcp_test),
    path("mcp/<int:mcp_id>/tools/", views.mcp_tools),
]
