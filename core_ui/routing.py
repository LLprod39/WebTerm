"""WebSocket routes for core_ui (Operator chat)."""

from django.urls import path

from core_ui.consumers import OperatorChatConsumer

websocket_urlpatterns = [
    path("ws/operator/<int:chat_id>/", OperatorChatConsumer.as_asgi()),
]
