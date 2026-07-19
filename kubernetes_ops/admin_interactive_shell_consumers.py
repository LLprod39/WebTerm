from __future__ import annotations

import asyncio

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from kubernetes_ops.consumers import KubernetesAdminConsumerAuthMixin, _exec_stream_requested
from kubernetes_ops.continuous_interactive_shell_streams import (
    run_provider_cluster_terminal_stream,
    run_provider_node_debug_stream,
)
from kubernetes_ops.services.admin_node_debug import prepare_node_debug_start
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_terminal import prepare_cluster_terminal_start


class KubernetesAdminClusterTerminalStreamConsumer(KubernetesAdminConsumerAuthMixin, AsyncJsonWebsocketConsumer):
    _terminal_task: asyncio.Task | None = None
    _terminal_input_queue: asyncio.Queue | None = None

    async def connect(self):
        if not self._authenticated():
            await self.close(code=4001)
            return
        await self.accept()
        params = self._query_params()
        if _exec_stream_requested(params):
            self._terminal_input_queue = asyncio.Queue()
            self._terminal_task = asyncio.create_task(run_provider_cluster_terminal_stream(self, params, self._terminal_input_queue))
            return
        try:
            session = await database_sync_to_async(_session_for_url)(self)
            envelope = await database_sync_to_async(prepare_cluster_terminal_start)(
                user=self.scope["user"],
                session=session,
                reason=params.get("reason", ""),
                include_restricted_context=False,
            )
        except AdminResourceError as exc:
            await self.send_json({"type": "terminal_rejected", "code": exc.code, "message": str(exc), "payload": exc.payload})
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json({"type": "terminal_blocked", "stream_type": "cluster_terminal", "payload": envelope})
        await self.close(code=4403)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
            return
        if self._terminal_input_queue is not None and content.get("type") in {"stdin", "terminal_input"}:
            await self._terminal_input_queue.put(str(content.get("data") or ""))

    async def disconnect(self, code):
        task = self._terminal_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return


class KubernetesAdminNodeDebugStreamConsumer(KubernetesAdminConsumerAuthMixin, AsyncJsonWebsocketConsumer):
    _node_debug_task: asyncio.Task | None = None
    _node_debug_input_queue: asyncio.Queue | None = None

    async def connect(self):
        if not self._authenticated():
            await self.close(code=4001)
            return
        await self.accept()
        params = self._query_params()
        if _exec_stream_requested(params):
            self._node_debug_input_queue = asyncio.Queue()
            self._node_debug_task = asyncio.create_task(run_provider_node_debug_stream(self, params, self._node_debug_input_queue))
            return
        try:
            session = await database_sync_to_async(_session_for_url)(self)
            envelope = await database_sync_to_async(prepare_node_debug_start)(
                user=self.scope["user"],
                session=session,
                node_name=params.get("node") or params.get("node_name") or params.get("name", ""),
                reason=params.get("reason", ""),
            )
        except AdminResourceError as exc:
            await self.send_json({"type": "node_debug_rejected", "code": exc.code, "message": str(exc), "payload": exc.payload})
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json({"type": "node_debug_blocked", "stream_type": "node_debug", "payload": envelope})
        await self.close(code=4403)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
            return
        if self._node_debug_input_queue is not None and content.get("type") in {"stdin", "node_debug_input"}:
            await self._node_debug_input_queue.put(str(content.get("data") or ""))

    async def disconnect(self, code):
        task = self._node_debug_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return


def _session_for_url(consumer):
    from kubernetes_ops.models import K8sAdminSession

    session = (
        K8sAdminSession.objects.select_related("cluster", "cluster__rancher_provider")
        .filter(session_id=str(consumer.scope["url_route"]["kwargs"]["session_id"]), user=consumer.scope["user"])
        .first()
    )
    if session is None:
        raise AdminResourceError("Active admin session is required.", code="admin_session_required", status=403)
    return session
