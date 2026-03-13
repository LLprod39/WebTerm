"""
WebSocket consumer for live monitoring of full ReAct agents.

Clients connect to /ws/agents/<run_id>/live/ and receive streaming events:
  agent_thought, agent_action, agent_observation, agent_console,
  agent_status, agent_report, agent_question

Clients can send:
  agent_reply, agent_stop, agent_pause, agent_resume
"""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from servers.agent_runtime import get_engine_for_run, update_runtime_control


class AgentLiveConsumer(AsyncJsonWebsocketConsumer):
    """
    Read-mostly WebSocket consumer for observing a running agent.

    The actual agent execution happens in AgentEngine (kicked off by the HTTP
    view or a background task). This consumer subscribes to a Channels group
    keyed by run_id and forwards events to the browser.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.run_id: int | None = None
        self.group_name: str = ""
        self._user_id: int | None = None

    async def connect(self):
        self.run_id = int(self.scope["url_route"]["kwargs"]["run_id"])
        self.group_name = f"agent_run_{self.run_id}"

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self._user_id = user.id

        has_access = await self._check_access()
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        run_data = await self._get_run_snapshot()
        await self.send_json({"type": "agent_init", **run_data})

    async def disconnect(self, code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type", "")

        if msg_type == "agent_stop":
            await self._handle_stop()
        elif msg_type == "agent_pause":
            await self._handle_pause()
        elif msg_type == "agent_resume":
            await self._handle_resume()
        elif msg_type == "agent_reply":
            await self._handle_reply(content.get("answer", ""))
        elif msg_type == "ping":
            await self.send_json({"type": "pong"})

    # ------------------------------------------------------------------
    # Group message handlers (sent by AgentEngine via channel layer)
    # ------------------------------------------------------------------

    async def agent_thought(self, event):
        await self.send_json(event)

    async def agent_action(self, event):
        await self.send_json(event)

    async def agent_observation(self, event):
        await self.send_json(event)

    async def agent_console(self, event):
        await self.send_json(event)

    async def agent_status(self, event):
        await self.send_json(event)

    async def agent_report(self, event):
        await self.send_json(event)

    async def agent_question(self, event):
        await self.send_json(event)

    async def agent_plan(self, event):
        await self.send_json(event)

    async def agent_pipeline_phase(self, event):
        await self.send_json(event)

    async def agent_task_start(self, event):
        await self.send_json(event)

    async def agent_task_done(self, event):
        await self.send_json(event)

    async def agent_task_failed(self, event):
        await self.send_json(event)

    async def agent_task_iteration(self, event):
        await self.send_json(event)

    # ------------------------------------------------------------------
    # User commands
    # ------------------------------------------------------------------

    async def _handle_stop(self):
        await self._issue_runtime_control(stop_requested=True, pause_requested=False)
        await self._mark_run_stopped()
        await self.channel_layer.group_send(self.group_name, {
            "type": "agent_status",
            "status": "stopped",
            "reason": "user_requested",
        })

    async def _handle_pause(self):
        from servers.models import AgentRun
        await self._issue_runtime_control(pause_requested=True)
        await self._update_run_status(AgentRun.STATUS_PAUSED)
        await self.channel_layer.group_send(self.group_name, {
            "type": "agent_status",
            "status": "paused",
        })

    async def _handle_resume(self):
        from servers.models import AgentRun
        await self._issue_runtime_control(pause_requested=False)
        await self._update_run_status(AgentRun.STATUS_RUNNING)
        await self.channel_layer.group_send(self.group_name, {
            "type": "agent_status",
            "status": "running",
        })

    async def _handle_reply(self, answer: str):
        if not answer:
            return
        from servers.models import AgentRun
        await self._issue_runtime_control(reply_text=answer, pause_requested=False)

        @database_sync_to_async
        def save_reply():
            run = AgentRun.objects.filter(id=self.run_id).first()
            if run and run.status == AgentRun.STATUS_WAITING:
                run.pending_question = ""
                run.status = AgentRun.STATUS_RUNNING
                run.save(update_fields=["pending_question", "status"])

        await save_reply()
        await self.channel_layer.group_send(self.group_name, {
            "type": "agent_status",
            "status": "running",
            "user_reply": answer,
        })

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @database_sync_to_async
    def _check_access(self) -> bool:
        from django.contrib.auth.models import User
        from core_ui.context_processors import user_can_feature
        from servers.models import AgentRun

        user = User.objects.filter(id=self._user_id).first()
        if not user or not user_can_feature(user, "agents"):
            return False

        return AgentRun.objects.filter(
            id=self.run_id, agent__user_id=self._user_id,
        ).exists()

    @database_sync_to_async
    def _get_run_snapshot(self) -> dict:
        from servers.models import AgentRun
        run = AgentRun.objects.filter(id=self.run_id).select_related("agent", "server").first()
        if not run:
            return {"error": "Run not found"}
        return {
            "run_id": run.id,
            "agent_name": run.agent.name,
            "agent_mode": run.agent.mode,
            "status": run.status,
            "total_iterations": run.total_iterations,
            "connected_servers": run.connected_servers or [],
            "pending_question": run.pending_question,
            "iterations_count": len(run.iterations_log or []),
        }

    @database_sync_to_async
    def _update_run_status(self, status: str):
        from servers.models import AgentRun
        AgentRun.objects.filter(id=self.run_id, agent__user_id=self._user_id).update(status=status)

    @database_sync_to_async
    def _mark_run_stopped(self):
        from django.utils import timezone
        from servers.models import AgentRun

        AgentRun.objects.filter(id=self.run_id, agent__user_id=self._user_id).update(
            status=AgentRun.STATUS_STOPPED,
            completed_at=timezone.now(),
        )

    @database_sync_to_async
    def _issue_runtime_control(
        self,
        *,
        stop_requested: bool | None = None,
        pause_requested: bool | None = None,
        reply_text: str | None = None,
    ):
        from servers.models import AgentRun

        run = AgentRun.objects.filter(id=self.run_id, agent__user_id=self._user_id).first()
        if not run:
            return
        live_engine = get_engine_for_run(self.run_id)
        update_runtime_control(
            run,
            live_engine=live_engine,
            stop_requested=stop_requested,
            pause_requested=pause_requested,
            reply_text=reply_text,
        )
