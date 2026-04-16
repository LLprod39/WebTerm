"""
WebSocket routes for servers app.
"""

from django.urls import path

from servers.consumers import AgentLiveConsumer, RDPTerminalConsumer, SSHTerminalConsumer

websocket_urlpatterns = [
    path("ws/servers/<int:server_id>/terminal/", SSHTerminalConsumer.as_asgi()),
    path("ws/servers/<int:server_id>/rdp/", RDPTerminalConsumer.as_asgi()),
    path("ws/agents/<int:run_id>/live/", AgentLiveConsumer.as_asgi()),
]

