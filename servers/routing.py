"""
WebSocket routes for servers app.
"""

from django.urls import path

from servers.consumers import AgentLiveConsumer, MonitoringLiveConsumer, SSHTerminalConsumer

websocket_urlpatterns = [
    path("ws/servers/<int:server_id>/terminal/", SSHTerminalConsumer.as_asgi()),
    path("ws/agents/<int:run_id>/live/", AgentLiveConsumer.as_asgi()),
    path("ws/monitoring/live/", MonitoringLiveConsumer.as_asgi()),
]
