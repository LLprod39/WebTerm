from __future__ import annotations

import asyncio
import base64
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor
from time import monotonic
from typing import Any

from channels.db import database_sync_to_async

from kubernetes_ops.services.admin_port_forward_tunnel import (
    complete_kubernetes_port_forward_tunnel,
    fail_kubernetes_port_forward_tunnel,
    prepare_kubernetes_port_forward_tunnel_context,
)
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_streams import active_admin_stream_session_status, bounded_stream_float, bounded_stream_int
from kubernetes_ops.services.provider_clients import KubernetesProviderError
from kubernetes_ops.services.provider_port_forward_tunnels import MAX_PROVIDER_TUNNEL_BYTES, open_provider_port_forward_tunnel


async def run_provider_port_forward_tunnel(consumer, params: dict[str, str], input_queue: asyncio.Queue[Any]) -> None:
    max_frames = bounded_stream_int(params.get("max_frames"), default=500, minimum=1, maximum=4000)
    idle_timeout = bounded_stream_float(params.get("idle_timeout_seconds"), default=300.0, minimum=5.0, maximum=1800.0)
    heartbeat_interval = bounded_stream_float(params.get("heartbeat_interval_seconds"), default=10.0, minimum=1.0, maximum=60.0)
    empty_read_sleep = bounded_stream_float(params.get("empty_read_sleep_seconds"), default=0.25, minimum=0.05, maximum=5.0)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="k8s-port-forward")
    loop = asyncio.get_running_loop()
    stream_handle = None
    context = None
    bytes_from_client = 0
    bytes_to_client = 0
    finalized = False
    close_reason = "max_frames"
    stream_closed = False
    try:
        context = await database_sync_to_async(prepare_kubernetes_port_forward_tunnel_context)(
            user=consumer.scope["user"],
            session_id=str(consumer.scope["url_route"]["kwargs"]["session_id"]),
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
        await consumer.send_json({"type": "port_forward_started", "stream_id": context["stream_id"], "stream_type": "port_forward", "payload": _public_context(context)})
        tunnel_timeout = bounded_stream_int(params.get("stream_timeout_seconds"), default=30, minimum=1, maximum=300)
        stream_handle = await loop.run_in_executor(
            executor,
            lambda: open_provider_port_forward_tunnel(
                context["_provider"],
                context["_tunnel_path"],
                timeout=tunnel_timeout,
                target=context["target"],
                duration_seconds=context["duration_seconds"],
            ),
        )
        started = monotonic()
        last_heartbeat = started
        for frame_index in range(1, max_frames + 1):
            elapsed = monotonic() - started
            if elapsed >= float(context["duration_seconds"]):
                close_reason = "duration_limit"
                break
            if elapsed >= idle_timeout:
                close_reason = "idle_timeout"
                break
            session_state = await database_sync_to_async(active_admin_stream_session_status)(session_pk=context["_session_pk"])
            if not session_state.get("active"):
                close_reason = str(session_state.get("code") or "admin_session_not_active")
                break
            bytes_from_client += await _drain_client_data(consumer, stream_handle, input_queue, loop, executor)
            event = await loop.run_in_executor(executor, lambda: stream_handle.read_event(max_bytes=MAX_PROVIDER_TUNNEL_BYTES))
            if event.data:
                bytes_to_client += len(event.data)
                await consumer.send_json(
                    {
                        "type": "port_forward_data",
                        "stream_id": context["stream_id"],
                        "frame_index": frame_index,
                        "encoding": "base64",
                        "data": base64.b64encode(event.data).decode("ascii"),
                    }
                )
            if event.eof:
                close_reason = "provider_eof"
                break
            if not event.data:
                if monotonic() - last_heartbeat >= heartbeat_interval:
                    await consumer.send_json({"type": "port_forward_heartbeat", "stream_id": context["stream_id"], "frame_index": frame_index})
                    last_heartbeat = monotonic()
                await asyncio.sleep(empty_read_sleep)
        stream_closed = await _close_stream_handle(loop, executor, stream_handle)
        summary = await database_sync_to_async(complete_kubernetes_port_forward_tunnel)(
            user=consumer.scope["user"],
            action_id=context["action"]["id"],
            session_pk=context["_session_pk"],
            stream_id=context["stream_id"],
            bytes_from_client=bytes_from_client,
            bytes_to_client=bytes_to_client,
            close_reason=close_reason,
        )
        finalized = True
        await consumer.send_json({"type": "port_forward_stopped", "stream_id": context["stream_id"], "stream_type": "port_forward", "summary": summary})
        await consumer.close(code=1000)
    except asyncio.CancelledError:
        if not stream_closed:
            stream_closed = await _close_stream_handle(loop, executor, stream_handle)
        if context and not finalized:
            await database_sync_to_async(complete_kubernetes_port_forward_tunnel)(
                user=consumer.scope["user"],
                action_id=context["action"]["id"],
                session_pk=context["_session_pk"],
                stream_id=context["stream_id"],
                bytes_from_client=bytes_from_client,
                bytes_to_client=bytes_to_client,
                close_reason="client_disconnect",
            )
        raise
    except KubernetesProviderError as exc:
        if not stream_closed:
            stream_closed = await _close_stream_handle(loop, executor, stream_handle)
        if context:
            summary = await database_sync_to_async(fail_kubernetes_port_forward_tunnel)(
                user=consumer.scope["user"],
                action_id=context["action"]["id"],
                session_pk=context["_session_pk"],
                stream_id=context["stream_id"],
                error_code="provider_port_forward_tunnel_error",
                bytes_from_client=bytes_from_client,
                bytes_to_client=bytes_to_client,
            )
            await consumer.send_json({"type": "port_forward_error", "code": "provider_port_forward_tunnel_error", "message": str(exc), "summary": summary})
        else:
            await consumer.send_json({"type": "port_forward_rejected", "code": "provider_port_forward_tunnel_error", "message": str(exc), "payload": {}})
        await consumer.close(code=4400)
    except AdminResourceError as exc:
        await consumer.send_json({"type": "port_forward_rejected", "code": exc.code, "message": str(exc), "payload": exc.payload})
        await consumer.close(code=4403 if exc.status == 403 else 4400)
    finally:
        if not stream_closed:
            await _close_stream_handle(loop, executor, stream_handle)
        executor.shutdown(wait=False, cancel_futures=True)


async def _drain_client_data(consumer, stream_handle, input_queue: asyncio.Queue[Any], loop, executor) -> int:
    total = 0
    while True:
        try:
            content = input_queue.get_nowait()
        except asyncio.QueueEmpty:
            return total
        data = _decode_client_data(content)
        if not data:
            continue
        accepted = await loop.run_in_executor(executor, lambda value=data: stream_handle.write_client_data(value))
        if accepted:
            total += len(data)
        else:
            await consumer.send_json({"type": "port_forward_input_rejected", "reason": "provider_client_data_not_supported"})


async def _close_stream_handle(loop, executor, stream_handle) -> bool:
    if stream_handle is None:
        return False
    with suppress(Exception):
        await loop.run_in_executor(executor, stream_handle.close)
        return True
    return False


def _decode_client_data(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if not isinstance(content, dict):
        return str(content or "").encode("utf-8")
    value = content.get("data", "")
    if str(content.get("encoding") or "").lower() == "base64":
        try:
            return base64.b64decode(str(value or ""))
        except (ValueError, TypeError):
            return b""
    return str(value or "").encode("utf-8")


def _public_context(context: dict) -> dict:
    return {key: value for key, value in context.items() if not key.startswith("_")}
