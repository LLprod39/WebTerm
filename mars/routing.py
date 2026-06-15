from django.urls import path

from mars.consumers import MarsRunConsumer

websocket_urlpatterns = [
    path("ws/mars/runs/<int:run_id>/live/", MarsRunConsumer.as_asgi()),
]
