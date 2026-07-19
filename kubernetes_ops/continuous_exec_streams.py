from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from channels.db import database_sync_to_async

from kubernetes_ops.services.admin_exec_stream import (
    complete_kubernetes_exec_stream,
    fail_kubernetes_exec_stream,
    prepare_kubernetes_exec_stream_context,
)
from kubernetes_ops.services.admin_recording import append_interactive_recording_event
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_streams import (
    active_admin_stream_session_status,
    bounded_stream_float,
    bounded_stream_int,
)
from kubernetes_ops.services.logs import _redact_log_line, _trim_log_line
from kubernetes_ops.services.provider_clients import KubernetesProviderError
from kubernetes_ops.services.provider_exec_streams import MAX_PROVIDER_EXEC_STREAM_BYTES, open_provider_exec_stream


async def run_provider_exec_stream(consumer, params: dict[str, str], input_queue: asyncio.Queue[str]) -> None:
    max_frames = bounded_stream_int(params.get("max_frames"), default=250, minimum=1, maximum=2000)
    idle_timeout = bounded_stream_float(params.get("idle_timeout_seconds"), default=300.0, minimum=5.0, maximum=1800.0)
    heartbeat_interval = bounded_stream_float(params.get("heartbeat_interval_seconds"), default=10.0, minimum=1.0, maximum=60.0)
    empty_read_sleep = bounded_stream_float(params.get("empty_read_sleep_seconds"), default=0.25, minimum=0.05, maximum=5.0)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="k8s-exec-stream")
    loop = asyncio.get_running_loop()
    stream_handle = None
    context = None
    stdout_count = 0
    stderr_count = 0
    exit_code = None
    finalized = False
    close_reason = "max_frames"
    try:
        context = await database_sync_to_async(prepare_kubernetes_exec_stream_context)(
            user=consumer.scope["user"],
            session_id=str(consumer.scope["url_route"]["kwargs"]["session_id"]),
            cluster_id=params.get("cluster_id", ""),
            namespace=params.get("namespace", ""),
            pod_name=params.get("pod") or params.get("name", ""),
            container=params.get("container", ""),
            command=params.get("command", ""),
            reason=params.get("reason", ""),
            tty=_truthy(params.get("tty")),
            stdin=_truthy(params.get("stdin")),
            timeout_seconds=params.get("stream_timeout_seconds", ""),
        )
        await consumer.send_json({"type": "exec_started", "stream_id": context["stream_id"], "stream_type": "exec", "payload": _public_context(context)})
        stream_handle = await loop.run_in_executor(
            executor,
            lambda: open_provider_exec_stream(
                context["_provider"],
                context["_exec_path"],
                timeout=context["_timeout_seconds"],
                command=context["_command_parts"],
                container=context["target"].get("container", ""),
                tty=bool(context.get("tty")),
                stdin=bool(context.get("stdin")),
            ),
        )
        last_heartbeat = monotonic()
        for frame_index in range(1, max_frames + 1):
            if monotonic() - _started_monotonic(context) >= idle_timeout:
                close_reason = "idle_timeout"
                break
            session_state = await database_sync_to_async(active_admin_stream_session_status)(session_pk=context["_session_pk"])
            if not session_state.get("active"):
                close_reason = str(session_state.get("code") or "admin_session_not_active")
                break
            await _drain_stdin(consumer, stream_handle, input_queue, loop, executor, context=context, sequence=frame_index)
            try:
                event = await loop.run_in_executor(executor, lambda: stream_handle.read_event(max_bytes=MAX_PROVIDER_EXEC_STREAM_BYTES))
            except KubernetesProviderError as exc:
                finalized = True
                summary = await database_sync_to_async(fail_kubernetes_exec_stream)(
                    user=consumer.scope["user"],
                    action_id=context["action"]["id"],
                    session_pk=context["_session_pk"],
                    stream_id=context["stream_id"],
                    error_code="provider_exec_stream_error",
                    stdout_count=stdout_count,
                    stderr_count=stderr_count,
                )
                await consumer.send_json({"type": "exec_error", "code": "provider_exec_stream_error", "message": str(exc), "summary": summary})
                await consumer.close(code=4400)
                return
            if event.stream == "heartbeat" and not event.eof:
                if monotonic() - last_heartbeat >= heartbeat_interval:
                    await consumer.send_json({"type": "exec_heartbeat", "stream_id": context["stream_id"], "frame_index": frame_index})
                    last_heartbeat = monotonic()
                await asyncio.sleep(empty_read_sleep)
                continue
            if event.stream in {"stdout", "stderr"} and event.data:
                if event.stream == "stdout":
                    stdout_count += 1
                else:
                    stderr_count += 1
                redacted_data = _redact_exec_output(event.data)
                await database_sync_to_async(append_interactive_recording_event)(
                    recording_pk=context["_recording_pk"],
                    stream=event.stream,
                    data=event.data,
                    sequence=frame_index,
                    metadata={"source": "provider_exec_stream"},
                )
                await consumer.send_json(
                    {
                        "type": "exec_output",
                        "stream_id": context["stream_id"],
                        "stream": event.stream,
                        "frame_index": frame_index,
                        "data": redacted_data,
                    }
                )
            if event.exit_code is not None:
                exit_code = event.exit_code
            if event.eof:
                close_reason = "provider_eof"
                break
        summary = await database_sync_to_async(complete_kubernetes_exec_stream)(
            user=consumer.scope["user"],
            action_id=context["action"]["id"],
            session_pk=context["_session_pk"],
            stream_id=context["stream_id"],
            stdout_count=stdout_count,
            stderr_count=stderr_count,
            exit_code=exit_code,
            close_reason=close_reason,
        )
        finalized = True
        if stream_handle is not None:
            await loop.run_in_executor(executor, stream_handle.close)
            stream_handle = None
        await consumer.send_json({"type": "exec_stopped", "stream_id": context["stream_id"], "stream_type": "exec", "summary": summary})
        await consumer.close(code=1000)
    except asyncio.CancelledError:
        if context and not finalized:
            await database_sync_to_async(complete_kubernetes_exec_stream)(
                user=consumer.scope["user"],
                action_id=context["action"]["id"],
                session_pk=context["_session_pk"],
                stream_id=context["stream_id"],
                stdout_count=stdout_count,
                stderr_count=stderr_count,
                exit_code=exit_code,
                close_reason="client_disconnect",
            )
        raise
    except AdminResourceError as exc:
        await consumer.send_json({"type": "exec_rejected", "code": exc.code, "message": str(exc), "payload": exc.payload})
        await consumer.close(code=4403 if exc.status == 403 else 4400)
    finally:
        if stream_handle is not None:
            await loop.run_in_executor(executor, stream_handle.close)
        executor.shutdown(wait=False, cancel_futures=True)


async def _drain_stdin(consumer, stream_handle, input_queue: asyncio.Queue[str], loop, executor, *, context: dict, sequence: int) -> None:
    while True:
        try:
            data = input_queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        accepted = await loop.run_in_executor(executor, lambda value=data: stream_handle.write_stdin(value))
        if not accepted:
            await consumer.send_json({"type": "exec_input_rejected", "reason": "provider_stdin_not_supported"})
            continue
        await database_sync_to_async(append_interactive_recording_event)(
            recording_pk=context["_recording_pk"],
            stream="stdin",
            data=data,
            sequence=sequence,
            metadata={"source": "client_stdin"},
        )


def _public_context(context: dict) -> dict:
    return {key: value for key, value in context.items() if not key.startswith("_")}


def _redact_exec_output(value: str) -> str:
    return _redact_log_line(_trim_log_line(str(value)))


def _started_monotonic(context: dict) -> float:
    value = context.setdefault("_started_monotonic", monotonic())
    return float(value)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
