from __future__ import annotations

import asyncio
import urllib.parse
from time import monotonic

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

from kubernetes_ops.continuous_exec_streams import run_provider_exec_stream
from kubernetes_ops.continuous_log_streams import run_continuous_log_follow
from kubernetes_ops.continuous_port_forward_tunnels import run_provider_port_forward_tunnel
from kubernetes_ops.continuous_watch_streams import run_continuous_watch_follow
from kubernetes_ops.services.admin_exec import prepare_kubernetes_exec_bridge
from kubernetes_ops.services.admin_logs import get_admin_pod_log_snapshot, get_admin_pod_log_stream_batch
from kubernetes_ops.services.admin_port_forward import prepare_kubernetes_port_forward_bridge
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_streams import (
    active_admin_stream_session_status,
    bounded_stream_float,
    bounded_stream_int,
    close_admin_stream,
    fail_admin_stream,
    open_admin_log_stream_snapshot,
    open_admin_watch_stream_snapshot,
    start_admin_log_stream,
    start_admin_watch_stream,
)
from kubernetes_ops.services.admin_watch import get_admin_resource_watch_preview, get_admin_resource_watch_stream_batch


class KubernetesAdminConsumerAuthMixin:
    def _authenticated(self) -> bool:
        user = self.scope.get("user")
        return bool(user and not isinstance(user, AnonymousUser) and user.is_authenticated)

    def _query_params(self) -> dict[str, str]:
        raw = self.scope.get("query_string", b"").decode("utf-8", errors="ignore")
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}


class KubernetesAdminFollowLifecycleMixin(KubernetesAdminConsumerAuthMixin):
    _active_stream: dict | None = None
    _last_payload: dict | None = None
    _batch_count: int = 0
    _stream_finalized: bool = False

    def _track_follow_stream(self, stream: dict, initial_payload: dict) -> None:
        self._active_stream = stream
        self._last_payload = initial_payload
        self._batch_count = 0
        self._stream_finalized = False

    def _track_follow_batch(self, payload: dict, batch_count: int) -> None:
        self._last_payload = payload
        self._batch_count = batch_count

    async def _close_active_stream(self, close_reason: str) -> dict | None:
        stream = self._active_stream
        if not stream or self._stream_finalized:
            return None
        self._stream_finalized = True
        return await database_sync_to_async(close_admin_stream)(
            user=self.scope["user"],
            stream=stream,
            last_payload=self._last_payload
            or {"target": stream.get("target", {}), "source": "not_started", "available": False},
            batch_count=self._batch_count,
            close_reason=close_reason,
        )

    async def _active_stream_session_close_reason(self, stream: dict) -> str:
        state = await database_sync_to_async(active_admin_stream_session_status)(session_pk=stream["session_pk"])
        if state.get("active"):
            return ""
        last_payload = dict(
            self._last_payload or {"target": stream.get("target", {}), "source": "not_started", "available": False}
        )
        last_payload["session_status"] = str(state.get("status") or "")
        self._last_payload = last_payload
        return str(state.get("code") or "admin_session_not_active")

    async def _fail_active_stream(self, stream: dict, exc: AdminResourceError) -> None:
        self._stream_finalized = True
        await self._fail_stream(stream, exc)

    async def disconnect(self, code):
        await self._close_active_stream("client_disconnect")


class KubernetesAdminLogStreamConsumer(KubernetesAdminFollowLifecycleMixin, AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not self._authenticated():
            await self.close(code=4001)
            return
        await self.accept()
        params = self._query_params()
        if _truthy(params.get("follow")):
            await self._follow(params)
            return
        try:
            envelope = await database_sync_to_async(open_admin_log_stream_snapshot)(
                user=self.scope["user"],
                session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                cluster_id=params.get("cluster_id", ""),
                namespace=params.get("namespace", ""),
                pod_name=params.get("pod") or params.get("name", ""),
                container=params.get("container", ""),
                tail_lines=params.get("tail", "120"),
            )
        except AdminResourceError as exc:
            await self.send_json(
                {"type": "stream_error", "code": exc.code, "message": str(exc), "payload": exc.payload}
            )
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json(_started_event(envelope))
        await self.send_json({"type": "log_batch", "stream_id": envelope["stream_id"], "payload": envelope["payload"]})
        await self.send_json(_stopped_event(envelope))
        await self.close(code=1000)

    async def _follow(self, params: dict[str, str]) -> None:
        try:
            stream = await database_sync_to_async(start_admin_log_stream)(
                user=self.scope["user"],
                session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                cluster_id=params.get("cluster_id", ""),
                namespace=params.get("namespace", ""),
                pod_name=params.get("pod") or params.get("name", ""),
                container=params.get("container", ""),
                follow=True,
            )
        except AdminResourceError as exc:
            await self.send_json(
                {"type": "stream_error", "code": exc.code, "message": str(exc), "payload": exc.payload}
            )
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json(_started_event(stream))
        self._track_follow_stream(
            stream, {"target": stream.get("target", {}), "source": "not_started", "available": False, "line_count": 0}
        )
        if _continuous_provider_stream(params):
            await run_continuous_log_follow(self, params, stream)
            return
        await self._log_follow_loop(params, stream)

    async def _log_follow_loop(self, params: dict[str, str], stream: dict) -> None:
        max_batches = bounded_stream_int(params.get("max_batches"), default=5, minimum=1, maximum=25)
        poll_interval = bounded_stream_float(
            params.get("poll_interval_seconds"), default=2.0, minimum=0.25, maximum=30.0
        )
        idle_timeout = bounded_stream_float(
            params.get("idle_timeout_seconds"), default=60.0, minimum=1.0, maximum=300.0
        )
        last_payload: dict = {
            "target": stream.get("target", {}),
            "source": "not_started",
            "available": False,
            "line_count": 0,
        }
        last_provider_payload: dict | None = None
        batch_count = 0
        close_reason = "max_batches"
        provider_stream = _truthy(params.get("provider_stream"))
        try:
            for batch_index in range(1, max_batches + 1):
                if monotonic() - float(stream["started_monotonic"]) >= idle_timeout:
                    close_reason = "idle_timeout"
                    break
                session_close_reason = await self._active_stream_session_close_reason(stream)
                if session_close_reason:
                    close_reason = session_close_reason
                    break
                try:
                    log_reader = get_admin_pod_log_stream_batch if provider_stream else get_admin_pod_log_snapshot
                    log_kwargs = {
                        "user": self.scope["user"],
                        "session_id": str(self.scope["url_route"]["kwargs"]["session_id"]),
                        "cluster_id": params.get("cluster_id", ""),
                        "namespace": params.get("namespace", ""),
                        "pod_name": params.get("pod") or params.get("name", ""),
                        "container": params.get("container", ""),
                        "tail_lines": params.get("tail", "120"),
                    }
                    if provider_stream:
                        log_kwargs["timeout_seconds"] = params.get("stream_timeout_seconds", "")
                    last_payload = await database_sync_to_async(log_reader)(**log_kwargs)
                except AdminResourceError as exc:
                    await self._fail_active_stream(stream, exc)
                    return
                provider_payload = last_payload
                last_payload = _deduplicate_log_follow_payload(last_provider_payload, provider_payload)
                last_provider_payload = provider_payload
                batch_count += 1
                self._track_follow_batch(last_payload, batch_count)
                await self.send_json(
                    {
                        "type": "log_batch",
                        "stream_id": stream["stream_id"],
                        "batch_index": batch_index,
                        "payload": last_payload,
                    }
                )
                if batch_index < max_batches:
                    await self.send_json(
                        {"type": "stream_heartbeat", "stream_id": stream["stream_id"], "batch_index": batch_index}
                    )
                    await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            await self._close_active_stream("client_disconnect")
            raise
        summary = await self._close_active_stream(close_reason)
        if summary is None:
            return
        await self.send_json(
            _stopped_event({"stream_id": stream["stream_id"], "stream_type": "logs", "summary": summary})
        )
        await self.close(code=1000)

    async def _fail_stream(self, stream: dict, exc: AdminResourceError) -> None:
        duration_ms = max(0, int((monotonic() - float(stream["started_monotonic"])) * 1000))
        await database_sync_to_async(fail_admin_stream)(
            user=self.scope["user"],
            session_pk=stream["session_pk"],
            stream_id=stream["stream_id"],
            stream_type=stream["stream_type"],
            error_code=exc.code,
            duration_ms=duration_ms,
        )
        await self.send_json({"type": "stream_error", "code": exc.code, "message": str(exc), "payload": exc.payload})
        await self.close(code=4403 if exc.status == 403 else 4400)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})


class KubernetesAdminWatchStreamConsumer(KubernetesAdminFollowLifecycleMixin, AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not self._authenticated():
            await self.close(code=4001)
            return
        await self.accept()
        params = self._query_params()
        if _truthy(params.get("follow")):
            await self._follow(params)
            return
        try:
            envelope = await database_sync_to_async(open_admin_watch_stream_snapshot)(
                user=self.scope["user"],
                session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                cluster_id=params.get("cluster_id", ""),
                api_version=params.get("api_version", "v1"),
                kind=params.get("kind", ""),
                namespace=params.get("namespace", ""),
                name=params.get("name", ""),
                resource=params.get("resource", ""),
                resource_version=params.get("resource_version", ""),
                limit=params.get("limit", "20"),
                timeout_seconds=params.get("timeout_seconds", "10"),
            )
        except AdminResourceError as exc:
            await self.send_json(
                {"type": "stream_error", "code": exc.code, "message": str(exc), "payload": exc.payload}
            )
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json(_started_event(envelope))
        await self.send_json(
            {"type": "watch_batch", "stream_id": envelope["stream_id"], "payload": envelope["payload"]}
        )
        await self.send_json(_stopped_event(envelope))
        await self.close(code=1000)

    async def _follow(self, params: dict[str, str]) -> None:
        try:
            stream = await database_sync_to_async(start_admin_watch_stream)(
                user=self.scope["user"],
                session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                cluster_id=params.get("cluster_id", ""),
                api_version=params.get("api_version", "v1"),
                kind=params.get("kind", ""),
                namespace=params.get("namespace", ""),
                name=params.get("name", ""),
                resource=params.get("resource", ""),
                follow=True,
            )
        except AdminResourceError as exc:
            await self.send_json(
                {"type": "stream_error", "code": exc.code, "message": str(exc), "payload": exc.payload}
            )
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json(_started_event(stream))
        self._track_follow_stream(
            stream, {"target": stream.get("target", {}), "source": "not_started", "available": False, "event_count": 0}
        )
        if _continuous_provider_stream(params):
            await run_continuous_watch_follow(self, params, stream)
            return
        await self._watch_follow_loop(params, stream)

    async def _watch_follow_loop(self, params: dict[str, str], stream: dict) -> None:
        max_batches = bounded_stream_int(params.get("max_batches"), default=5, minimum=1, maximum=25)
        poll_interval = bounded_stream_float(
            params.get("poll_interval_seconds"), default=2.0, minimum=0.25, maximum=30.0
        )
        idle_timeout = bounded_stream_float(
            params.get("idle_timeout_seconds"), default=60.0, minimum=1.0, maximum=300.0
        )
        last_payload: dict = {
            "target": stream.get("target", {}),
            "source": "not_started",
            "available": False,
            "event_count": 0,
        }
        batch_count = 0
        close_reason = "max_batches"
        next_resource_version = str(params.get("resource_version", "") or "")
        provider_stream = _truthy(params.get("provider_stream"))
        try:
            for batch_index in range(1, max_batches + 1):
                if monotonic() - float(stream["started_monotonic"]) >= idle_timeout:
                    close_reason = "idle_timeout"
                    break
                session_close_reason = await self._active_stream_session_close_reason(stream)
                if session_close_reason:
                    close_reason = session_close_reason
                    break
                try:
                    watch_reader = (
                        get_admin_resource_watch_stream_batch if provider_stream else get_admin_resource_watch_preview
                    )
                    last_payload = await database_sync_to_async(watch_reader)(
                        user=self.scope["user"],
                        session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                        cluster_id=params.get("cluster_id", ""),
                        api_version=params.get("api_version", "v1"),
                        kind=params.get("kind", ""),
                        namespace=params.get("namespace", ""),
                        name=params.get("name", ""),
                        resource=params.get("resource", ""),
                        resource_version=next_resource_version,
                        limit=params.get("limit", "20"),
                        timeout_seconds=params.get("timeout_seconds", "10"),
                    )
                except AdminResourceError as exc:
                    await self._fail_active_stream(stream, exc)
                    return
                next_resource_version = str(last_payload.get("latest_resource_version") or next_resource_version)
                batch_count += 1
                self._track_follow_batch(last_payload, batch_count)
                await self.send_json(
                    {
                        "type": "watch_batch",
                        "stream_id": stream["stream_id"],
                        "batch_index": batch_index,
                        "payload": last_payload,
                    }
                )
                if batch_index < max_batches:
                    await self.send_json(
                        {"type": "stream_heartbeat", "stream_id": stream["stream_id"], "batch_index": batch_index}
                    )
                    await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            await self._close_active_stream("client_disconnect")
            raise
        summary = await self._close_active_stream(close_reason)
        if summary is None:
            return
        await self.send_json(
            _stopped_event({"stream_id": stream["stream_id"], "stream_type": "watch", "summary": summary})
        )
        await self.close(code=1000)

    async def _fail_stream(self, stream: dict, exc: AdminResourceError) -> None:
        duration_ms = max(0, int((monotonic() - float(stream["started_monotonic"])) * 1000))
        await database_sync_to_async(fail_admin_stream)(
            user=self.scope["user"],
            session_pk=stream["session_pk"],
            stream_id=stream["stream_id"],
            stream_type=stream["stream_type"],
            error_code=exc.code,
            duration_ms=duration_ms,
        )
        await self.send_json({"type": "stream_error", "code": exc.code, "message": str(exc), "payload": exc.payload})
        await self.close(code=4403 if exc.status == 403 else 4400)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})


class KubernetesAdminExecStreamConsumer(KubernetesAdminConsumerAuthMixin, AsyncJsonWebsocketConsumer):
    _exec_task: asyncio.Task | None = None
    _exec_input_queue: asyncio.Queue | None = None

    async def connect(self):
        if not self._authenticated():
            await self.close(code=4001)
            return
        await self.accept()
        params = self._query_params()
        if _exec_stream_requested(params):
            self._exec_input_queue = asyncio.Queue()
            self._exec_task = asyncio.create_task(run_provider_exec_stream(self, params, self._exec_input_queue))
            return
        try:
            envelope = await database_sync_to_async(prepare_kubernetes_exec_bridge)(
                user=self.scope["user"],
                session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                cluster_id=params.get("cluster_id", ""),
                namespace=params.get("namespace", ""),
                pod_name=params.get("pod") or params.get("name", ""),
                container=params.get("container", ""),
                command=params.get("command", ""),
                reason=params.get("reason", ""),
                tty=_truthy(params.get("tty")),
                stdin=_truthy(params.get("stdin")),
            )
        except AdminResourceError as exc:
            await self.send_json(
                {"type": "exec_rejected", "code": exc.code, "message": str(exc), "payload": exc.payload}
            )
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json(
            {"type": "exec_blocked", "stream_id": envelope["stream_id"], "stream_type": "exec", "payload": envelope}
        )
        await self.close(code=4403)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
            return
        if self._exec_input_queue is not None and content.get("type") in {"stdin", "exec_input"}:
            await self._exec_input_queue.put(str(content.get("data") or ""))

    async def disconnect(self, code):
        task = self._exec_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return


class KubernetesAdminPortForwardStreamConsumer(KubernetesAdminConsumerAuthMixin, AsyncJsonWebsocketConsumer):
    _port_forward_task: asyncio.Task | None = None
    _port_forward_input_queue: asyncio.Queue | None = None

    async def connect(self):
        if not self._authenticated():
            await self.close(code=4001)
            return
        await self.accept()
        params = self._query_params()
        if _port_forward_tunnel_requested(params):
            self._port_forward_input_queue = asyncio.Queue()
            self._port_forward_task = asyncio.create_task(
                run_provider_port_forward_tunnel(self, params, self._port_forward_input_queue)
            )
            return
        try:
            envelope = await database_sync_to_async(prepare_kubernetes_port_forward_bridge)(
                user=self.scope["user"],
                session_id=str(self.scope["url_route"]["kwargs"]["session_id"]),
                cluster_id=params.get("cluster_id", ""),
                api_version=params.get("api_version", "v1"),
                kind=params.get("kind", "Service"),
                namespace=params.get("namespace", ""),
                name=params.get("name", ""),
                resource=params.get("resource", ""),
                remote_port=params.get("remote_port", ""),
                local_port=params.get("local_port", ""),
                duration_seconds=params.get("duration_seconds", ""),
                reason=params.get("reason", ""),
            )
        except AdminResourceError as exc:
            await self.send_json(
                {"type": "port_forward_rejected", "code": exc.code, "message": str(exc), "payload": exc.payload}
            )
            await self.close(code=4403 if exc.status == 403 else 4400)
            return
        await self.send_json(
            {
                "type": "port_forward_blocked",
                "stream_id": envelope["stream_id"],
                "stream_type": "port_forward",
                "payload": envelope,
            }
        )
        await self.close(code=4403)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
            return
        if self._port_forward_input_queue is not None and content.get("type") in {
            "client_data",
            "data",
            "port_forward_data",
        }:
            await self._port_forward_input_queue.put(content)

    async def disconnect(self, code):
        task = self._port_forward_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return


def _started_event(envelope: dict) -> dict:
    return {
        "type": "stream_started",
        "stream_id": envelope["stream_id"],
        "stream_type": envelope["stream_type"],
        "started_at": envelope["started_at"],
    }


def _stopped_event(envelope: dict) -> dict:
    return {
        "type": "stream_stopped",
        "stream_id": envelope["stream_id"],
        "stream_type": envelope["stream_type"],
        "summary": envelope["summary"],
    }


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "follow"}


def _continuous_provider_stream(params: dict[str, str]) -> bool:
    provider_stream = str(params.get("provider_stream") or "").strip().lower()
    transport = str(params.get("stream_transport") or "").strip().lower()
    return provider_stream == "continuous" or (
        _truthy(provider_stream) and transport in {"continuous", "provider_native"}
    )


def _exec_stream_requested(params: dict[str, str]) -> bool:
    provider_stream = str(params.get("provider_stream") or "").strip().lower()
    return _truthy(provider_stream) or _truthy(params.get("stream"))


def _port_forward_tunnel_requested(params: dict[str, str]) -> bool:
    return _exec_stream_requested(params) or _truthy(params.get("tunnel"))


def _deduplicate_log_follow_payload(previous_payload: dict | None, current_payload: dict) -> dict:
    previous_lines = previous_payload.get("lines") if isinstance(previous_payload, dict) else []
    current_lines = current_payload.get("lines")
    if (
        not isinstance(previous_lines, list)
        or not isinstance(current_lines, list)
        or not previous_lines
        or not current_lines
    ):
        return current_payload
    overlap = min(len(previous_lines), len(current_lines))
    duplicate_count = 0
    for size in range(overlap, 0, -1):
        if previous_lines[-size:] == current_lines[:size]:
            duplicate_count = size
            break
    if duplicate_count <= 0:
        return current_payload
    lines = current_lines[duplicate_count:]
    payload = dict(current_payload)
    payload["lines"] = lines
    payload["line_count"] = len(lines)
    payload["follow_delta"] = True
    payload["deduped_line_count"] = duplicate_count
    return payload
