"""
ASGI WebSocket routing.

We keep this separated so apps (e.g. servers/) can register their WS URLs.
"""

from servers.routing import websocket_urlpatterns as servers_websocket_urlpatterns
from studio.routing import websocket_urlpatterns as studio_websocket_urlpatterns

websocket_urlpatterns = [
    *servers_websocket_urlpatterns,
    *studio_websocket_urlpatterns,
]

