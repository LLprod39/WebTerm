from __future__ import annotations

import asyncio
import inspect
import uuid
from contextlib import suppress
from typing import Any

from django.utils.module_loading import import_string


async def verify_channel_layer_config(layer_config: dict[str, Any], *, timeout: float = 3.0) -> dict[str, Any]:
    backend = str(layer_config.get("BACKEND") or "").strip()
    if not backend:
        raise ValueError("CHANNEL_LAYERS['default'].BACKEND is required")

    config = dict(layer_config.get("CONFIG") or {})
    layer_cls = import_string(backend)
    receiver = layer_cls(**config)
    sender = receiver if backend == "channels.layers.InMemoryChannelLayer" else layer_cls(**config)

    probe = uuid.uuid4().hex
    group_name = f"health.group.{probe}"
    group_channel = await receiver.new_channel("health.group.")
    direct_channel = await receiver.new_channel("health.direct.")

    try:
        await receiver.group_add(group_name, group_channel)

        group_payload = {"type": "health.group", "probe": probe}
        await sender.group_send(group_name, group_payload)
        group_message = await asyncio.wait_for(receiver.receive(group_channel), timeout)

        direct_payload = {"type": "health.direct", "probe": probe}
        await sender.send(direct_channel, direct_payload)
        direct_message = await asyncio.wait_for(receiver.receive(direct_channel), timeout)
    finally:
        with suppress(Exception):
            await receiver.group_discard(group_name, group_channel)
        if sender is not receiver:
            await _close_layer(sender)
        await _close_layer(receiver)

    if group_message.get("probe") != probe:
        raise RuntimeError("Group message probe mismatch")
    if direct_message.get("probe") != probe:
        raise RuntimeError("Direct message probe mismatch")

    return {
        "backend": backend,
        "group_name": group_name,
        "group_channel": group_channel,
        "direct_channel": direct_channel,
    }


async def _close_layer(layer: Any) -> None:
    closer = getattr(layer, "close_pools", None) or getattr(layer, "close", None)
    if closer is None:
        return
    result = closer()
    if inspect.isawaitable(result):
        await result
