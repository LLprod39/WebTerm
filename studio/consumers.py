"""
WebSocket consumer for Pipeline Run live updates.

Channel group: pipeline_run_{run_id}
URL: /ws/studio/pipeline-runs/<run_id>/live/
"""

from __future__ import annotations

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from .pipeline_runtime import get_executor_for_run


class PipelineRunConsumer(AsyncWebsocketConsumer):
    async def _send_event(self, payload: dict):
        await self.send(text_data=json.dumps(payload, cls=DjangoJSONEncoder, ensure_ascii=False))

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
        self.group_name = f"pipeline_run_{run_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            msg = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = msg.get("action")
        if action == "stop":
            executor = get_executor_for_run(self.run_id)
            if executor is not None:
                executor.request_stop()
            await self._mark_run_stopped(self.run_id)
            await self._send_event(
                {"type": "control_ack", "action": "stop", "ok": True, "live_executor": executor is not None}
            )

    # ------------------------------------------------------------------
    # Handlers for group messages
    # ------------------------------------------------------------------

    async def pipeline_node_event(self, event):
        await self._send_event({"type": "node_event", **event})

    async def pipeline_node_state(self, event):
        await self._send_event({"type": "node_state", **event})

    async def pipeline_status(self, event):
        await self._send_event({"type": "run_status", **event})

    async def pipeline_control(self, event):
        # Forwarded to all consumers in the group (including executor task)
        pass

    @database_sync_to_async
    def _user_can_access_run(self, user_id: int, run_id: int) -> bool:
        from django.contrib.auth.models import User
        from core_ui.context_processors import user_can_feature
        from studio.models import PipelineRun

        user = User.objects.filter(id=user_id).first()
        if not user or not user_can_feature(user, "studio"):
            return False
        return PipelineRun.objects.filter(pk=run_id, pipeline__owner_id=user_id).exists()

    @database_sync_to_async
    def _mark_run_stopped(self, run_id: int) -> None:
        from studio.models import PipelineRun
        from studio.pipeline_runtime import update_runtime_control

        run = PipelineRun.objects.filter(pk=run_id).first()
        if run is None:
            return

        update_runtime_control(run, stop_requested=True)
        if run.status in {PipelineRun.STATUS_PENDING, PipelineRun.STATUS_RUNNING}:
            run.status = PipelineRun.STATUS_STOPPED
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "finished_at"])
