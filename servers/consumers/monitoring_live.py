"""
WebSocket consumer for live fleet metrics.

Clients connect to /ws/monitoring/live/ and send:
  {"type": "subscribe", "server_ids": [1, 2, ...]}

They then receive per-server samples every few seconds:
  {"type": "live.metrics", "server_id": 1, "cpu_percent": ..., ...}
  {"type": "live.state", "server_id": 1, "state": "streaming" | "connecting" | "error" | "stopped"}

Collectors are shared: one SSH session per host:port regardless of viewer count
or how many inventory rows (users) point at the same host
(see servers/monitoring_live.py). Disconnecting unsubscribes automatically.
"""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import User

from core_ui.context_processors import user_can_feature
from servers.monitoring_live import live_group_name, live_metrics_manager

MAX_LIVE_SUBSCRIPTIONS = 100


class MonitoringLiveConsumer(AsyncJsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id: int | None = None
        self._subscribed: set[int] = set()

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return
        self._user_id = user.id

        if not await self._has_feature():
            await self.close()
            return

        await self.accept()

    async def disconnect(self, code):
        for server_id in list(self._subscribed):
            await self.channel_layer.group_discard(live_group_name(server_id), self.channel_name)
            await live_metrics_manager.unsubscribe(server_id)
        self._subscribed.clear()

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type", "")
        if msg_type == "subscribe":
            await self._handle_subscribe(content.get("server_ids") or [])
        elif msg_type == "ping":
            await self.send_json({"type": "pong"})

    async def _handle_subscribe(self, raw_ids) -> None:
        requested = {int(item) for item in raw_ids if str(item).strip().lstrip("-").isdigit()}
        requested = set(sorted(requested)[:MAX_LIVE_SUBSCRIPTIONS])
        allowed = await self._accessible_ssh_ids(requested)

        for server_id in self._subscribed - allowed:
            await self.channel_layer.group_discard(live_group_name(server_id), self.channel_name)
            await live_metrics_manager.unsubscribe(server_id)
        for server_id in allowed - self._subscribed:
            await self.channel_layer.group_add(live_group_name(server_id), self.channel_name)
            await live_metrics_manager.subscribe(server_id)

        self._subscribed = allowed
        await self.send_json({"type": "subscribed", "server_ids": sorted(allowed)})

    # ------------------------------------------------------------------
    # Group message handlers (sent by LiveMetricsManager collectors)
    # ------------------------------------------------------------------

    async def live_metrics(self, event):
        await self.send_json(event)

    async def live_state(self, event):
        await self.send_json(event)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _has_feature(self) -> bool:
        user = User.objects.filter(id=self._user_id).first()
        return bool(user and user_can_feature(user, "servers"))

    @database_sync_to_async
    def _accessible_ssh_ids(self, requested: set[int]) -> set[int]:
        if not requested:
            return set()
        from servers.views.server_helpers import _accessible_servers_queryset

        user = User.objects.filter(id=self._user_id).first()
        if not user:
            return set()
        qs = _accessible_servers_queryset(user).filter(id__in=requested, server_type="ssh", is_active=True)
        return set(qs.values_list("id", flat=True))
