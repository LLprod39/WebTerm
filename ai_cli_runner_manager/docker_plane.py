"""Readiness checks for the filtered Docker proxy plane."""

from __future__ import annotations

import os
from urllib.error import URLError
from urllib.request import urlopen


def docker_proxy_health_url(docker_host: str | None = None) -> str | None:
    host = (docker_host if docker_host is not None else os.getenv("DOCKER_HOST", "")).strip()
    if not host.startswith("tcp://"):
        return None
    return f"http://{host.removeprefix('tcp://').rstrip('/')}/health"


def docker_plane_is_ready(*, fake_runtime: bool = False, timeout_seconds: float = 2.0) -> bool:
    """Return True when fake runtime is enabled or the Docker proxy answers /health."""
    if fake_runtime:
        return True
    health_url = docker_proxy_health_url()
    if health_url is None:
        return False
    try:
        with urlopen(health_url, timeout=timeout_seconds) as response:  # noqa: S310 - internal DOCKER_HOST
            return int(response.status) == 200
    except (URLError, TimeoutError, ValueError, OSError):
        return False
