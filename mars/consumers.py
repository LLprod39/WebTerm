from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone


class MarsRunConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4001)
            return

        run_id = self.scope["url_route"]["kwargs"]["run_id"]
        if not await self._user_can_access_run(user.id, run_id):
            await self.close(code=4003)
            return

        self.run_id = run_id
        self.group_name = f"mars_run_{run_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if payload.get("action") == "stop":
            await self._request_stop(self.run_id)
            await self.send(text_data=json.dumps({"type": "control_ack", "action": "stop", "ok": True}))

    async def mars_event(self, event):
        await self.send(text_data=json.dumps({"type": "mars_event", "event": event["event"]}, cls=DjangoJSONEncoder))

    @database_sync_to_async
    def _user_can_access_run(self, user_id: int, run_id: int) -> bool:
        from django.contrib.auth.models import User

        from core_ui.context_processors import user_can_feature
        from mars.models import MarsRun
        from mars.services import ensure_personal_workspace

        user = User.objects.filter(id=user_id).first()
        if not user or not user_can_feature(user, "mars"):
            return False
        workspace = ensure_personal_workspace(user)
        return MarsRun.objects.filter(pk=run_id, user_id=user_id, workspace=workspace).exists()

    @database_sync_to_async
    def _request_stop(self, run_id: int) -> None:
        from mars.models import MarsRun
        from mars.services import record_event

        run = MarsRun.objects.filter(pk=run_id).first()
        if run is None:
            return
        control = dict(run.runtime_control or {})
        control["stop_requested"] = True
        run.runtime_control = control
        update_fields = ["runtime_control"]
        if run.status == MarsRun.STATUS_QUEUED:
            run.status = MarsRun.STATUS_STOPPED
            run.completed_at = timezone.now()
            update_fields += ["status", "completed_at"]
        run.save(update_fields=update_fields)
        record_event(run, "mars_stop_requested", "Stop requested by websocket")
