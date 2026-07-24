from __future__ import annotations


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
