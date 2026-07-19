from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from channels.db import database_sync_to_async

from kubernetes_ops.services.admin_logs import (
    build_admin_pod_log_continuous_payload,
    prepare_admin_pod_log_continuous_stream,
)
from kubernetes_ops.services.admin_resources import AdminResourceError
from kubernetes_ops.services.admin_streams import bounded_stream_float, bounded_stream_int
from kubernetes_ops.services.provider_clients import MAX_PROVIDER_LOG_STREAM_BYTES, KubernetesProviderError
from kubernetes_ops.services.provider_log_streams import open_provider_log_line_stream


async def run_continuous_log_follow(consumer, params: dict[str, str], stream: dict) -> None:
    max_batches = bounded_stream_int(params.get("max_batches"), default=5, minimum=1, maximum=25)
    batch_lines = bounded_stream_int(params.get("batch_lines"), default=20, minimum=1, maximum=200)
    idle_timeout = bounded_stream_float(params.get("idle_timeout_seconds"), default=60.0, minimum=1.0, maximum=300.0)
    heartbeat_interval = bounded_stream_float(params.get("heartbeat_interval_seconds"), default=10.0, minimum=1.0, maximum=60.0)
    empty_read_sleep = bounded_stream_float(params.get("empty_read_sleep_seconds"), default=0.25, minimum=0.05, maximum=5.0)
    close_reason = "max_batches"
    stream_handle = None
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="k8s-log-stream")
    loop = asyncio.get_running_loop()
    try:
        context = await database_sync_to_async(prepare_admin_pod_log_continuous_stream)(
            user=consumer.scope["user"],
            session_id=str(consumer.scope["url_route"]["kwargs"]["session_id"]),
            cluster_id=params.get("cluster_id", ""),
            namespace=params.get("namespace", ""),
            pod_name=params.get("pod") or params.get("name", ""),
            container=params.get("container", ""),
            tail_lines=params.get("tail", "120"),
            timeout_seconds=params.get("stream_timeout_seconds", ""),
        )
        consumer._last_payload = dict(context["payload"])
        stream_handle = await loop.run_in_executor(
            executor,
            lambda: open_provider_log_line_stream(context["provider"], context["path"], timeout=context["timeout_seconds"]),
        )
        last_heartbeat = monotonic()
        while consumer._batch_count < max_batches:
            if monotonic() - float(stream["started_monotonic"]) >= idle_timeout:
                close_reason = "idle_timeout"
                break
            session_close_reason = await consumer._active_stream_session_close_reason(stream)
            if session_close_reason:
                close_reason = session_close_reason
                break
            try:
                batch = await loop.run_in_executor(
                    executor,
                    lambda: stream_handle.read_batch(max_lines=batch_lines, max_bytes=MAX_PROVIDER_LOG_STREAM_BYTES),
                )
            except KubernetesProviderError as exc:
                await consumer._fail_active_stream(stream, AdminResourceError(str(exc), code="provider_stream_error", status=502))
                return
            if not batch.lines:
                if batch.eof:
                    close_reason = "provider_eof"
                    break
                if monotonic() - last_heartbeat >= heartbeat_interval:
                    await consumer.send_json({"type": "stream_heartbeat", "stream_id": stream["stream_id"], "batch_index": consumer._batch_count})
                    last_heartbeat = monotonic()
                await asyncio.sleep(empty_read_sleep)
                continue
            payload = build_admin_pod_log_continuous_payload(
                context,
                raw_lines=batch.lines,
                provider_truncated=batch.truncated,
                eof=batch.eof,
                line_limit=batch_lines,
            )
            consumer._track_follow_batch(payload, consumer._batch_count + 1)
            await consumer.send_json({"type": "log_batch", "stream_id": stream["stream_id"], "batch_index": consumer._batch_count, "payload": payload})
            if batch.eof:
                close_reason = "provider_eof"
                break
        summary = await consumer._close_active_stream(close_reason)
        if summary is not None:
            await consumer.send_json({"type": "stream_stopped", "stream_id": stream["stream_id"], "stream_type": "logs", "summary": summary})
            await consumer.close(code=1000)
    except asyncio.CancelledError:
        await consumer._close_active_stream("client_disconnect")
        raise
    except KubernetesProviderError as exc:
        await consumer._fail_active_stream(stream, AdminResourceError(str(exc), code="provider_stream_error", status=502))
    except AdminResourceError as exc:
        await consumer._fail_active_stream(stream, exc)
    finally:
        if stream_handle is not None:
            await loop.run_in_executor(executor, stream_handle.close)
        executor.shutdown(wait=False, cancel_futures=True)
