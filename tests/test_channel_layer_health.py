import asyncio

import pytest

from core_ui.channel_layer_health import verify_channel_layer_config


@pytest.mark.django_db
def test_verify_channel_layer_config_with_inmemory_backend():
    result = asyncio.run(
        verify_channel_layer_config({"BACKEND": "channels.layers.InMemoryChannelLayer"}, timeout=1.0)
    )

    assert result["backend"] == "channels.layers.InMemoryChannelLayer"
    assert result["group_name"].startswith("health.group.")
