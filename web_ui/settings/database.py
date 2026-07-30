from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .env_helpers import env_float, env_int


def build_channel_settings(*, debug: bool) -> dict[str, object]:
    channel_redis_url = os.getenv("CHANNEL_REDIS_URL", "").strip()
    if not channel_redis_url and not debug:
        channel_redis_url = os.getenv("CELERY_BROKER_URL", "").strip()
    if not debug and not channel_redis_url:
        raise ImproperlyConfigured(
            "CHANNEL_REDIS_URL (or CELERY_BROKER_URL) must be set when DJANGO_DEBUG=false. "
            "InMemoryChannelLayer is not supported for production or multi-worker runtime control."
        )
    if not channel_redis_url:
        return {
            "CHANNEL_REDIS_URL": channel_redis_url,
            "CHANNEL_LAYERS": {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
        }

    socket_timeout = max(env_float("CHANNEL_REDIS_SOCKET_TIMEOUT_SECONDS", 30.0), 6.0)
    connect_timeout = max(env_float("CHANNEL_REDIS_CONNECT_TIMEOUT_SECONDS", 5.0), 1.0)
    health_check_interval = max(env_int("CHANNEL_REDIS_HEALTH_CHECK_INTERVAL_SECONDS", 30), 0)
    return {
        "CHANNEL_REDIS_URL": channel_redis_url,
        "_CHANNEL_REDIS_SOCKET_TIMEOUT": socket_timeout,
        "_CHANNEL_REDIS_CONNECT_TIMEOUT": connect_timeout,
        "_CHANNEL_REDIS_HEALTH_CHECK_INTERVAL": health_check_interval,
        "CHANNEL_LAYERS": {
            "default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer",
                "CONFIG": {
                    "hosts": [
                        {
                            "address": channel_redis_url,
                            "socket_timeout": socket_timeout,
                            "socket_connect_timeout": connect_timeout,
                            "health_check_interval": health_check_interval,
                        }
                    ]
                },
            }
        },
    }


def build_cache_settings(*, redis_url: str) -> dict[str, object]:
    if not redis_url:
        return {
            "CACHES": {
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                    "LOCATION": "webterm-local-cache",
                    "TIMEOUT": 300,
                }
            }
        }
    return {
        "CACHES": {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": redis_url,
                "TIMEOUT": 300,
                "KEY_PREFIX": "webterm",
            }
        }
    }


def build_database_settings(*, base_dir: Path) -> dict[str, object]:
    use_postgres = os.getenv("POSTGRES_HOST") or os.getenv("POSTGRES_DB")
    if use_postgres:
        statement_timeout_ms = max(env_int("POSTGRES_STATEMENT_TIMEOUT_MS", 30000), 0)
        connection_max_age = max(env_int("POSTGRES_CONN_MAX_AGE_SECONDS", 60), 0)
        database = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "weu_platform"),
            "USER": os.getenv("POSTGRES_USER", "weu"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": connection_max_age,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "connect_timeout": 10,
                "options": f"-c statement_timeout={statement_timeout_ms}",
            },
        }
    else:
        database = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": base_dir / "db.sqlite3",
            "OPTIONS": {
                "timeout": 60,
            },
        }
    return {"DATABASES": {"default": database}}
