import asyncio
import os

import pytest
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db import connection

pytestmark = pytest.mark.skipif(
    os.getenv("WEBTERM_REQUIRE_EXTERNAL_TEST_SERVICES") != "1",
    reason="requires the explicit PostgreSQL/Redis CI integration lane",
)


@pytest.mark.django_db
def test_ci_database_is_postgresql():
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.django_db
def test_ci_redis_cache_roundtrip():
    cache.set("webterm:ci:cache", {"state": "ok"}, timeout=30)
    assert cache.get("webterm:ci:cache") == {"state": "ok"}
    cache.delete("webterm:ci:cache")


@pytest.mark.django_db
def test_ci_redis_channel_layer_roundtrip():
    async def scenario():
        layer = get_channel_layer()
        assert layer is not None
        channel = await layer.new_channel("webterm.ci.")
        await layer.send(channel, {"type": "ci.message", "state": "ok"})
        message = await asyncio.wait_for(layer.receive(channel), timeout=5)
        assert message == {"type": "ci.message", "state": "ok"}

    asyncio.run(scenario())
