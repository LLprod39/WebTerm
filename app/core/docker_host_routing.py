"""Route loopback targets to the Docker host when running inside a container.

WebTerm often stores servers/endpoints as ``127.0.0.1`` / ``localhost`` because
the web backend runs directly on the host (or in WSL with mirrored
networking).  Workers such as ``operator-execution`` and ``agent-execution``
run in Docker bridge containers where loopback points at the container
itself, so SSH (and local Ollama) connections are refused.  Inside a
container we transparently swap a loopback host for the Docker host alias
(``host.docker.internal`` by default), mirroring what the isolated Ansible
runtime already does.

Control via ``WEBTERM_ROUTE_LOOPBACK_TO_DOCKER_HOST``:

* ``1/true/yes/on``  – always route loopback targets;
* ``0/false/no/off`` – never route;
* unset / ``auto``   – route only when running inside a container.

The alias comes from ``WEBTERM_DOCKER_HOST_ALIAS`` (falls back to
``WEBTERM_ANSIBLE_DOCKER_HOST_ALIAS``, then ``host.docker.internal``).
Outside containers (default ``auto``) behaviour is unchanged.
"""

from __future__ import annotations

import ipaddress
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from loguru import logger

ROUTE_ENV = "WEBTERM_ROUTE_LOOPBACK_TO_DOCKER_HOST"
ALIAS_ENV = "WEBTERM_DOCKER_HOST_ALIAS"
_ANSIBLE_ALIAS_ENV = "WEBTERM_ANSIBLE_DOCKER_HOST_ALIAS"
DEFAULT_DOCKER_HOST_ALIAS = "host.docker.internal"

_HOST_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_TRUE = {"1", "true", "yes", "on"}
_LOGGED_ROUTES: set[tuple[str, str, str]] = set()
_FALSE = {"0", "false", "no", "off"}


@lru_cache(maxsize=1)
def running_in_container() -> bool:
    """Best-effort detection of a Docker/Podman container runtime."""
    for marker in ("/.dockerenv", "/run/.containerenv"):
        try:
            if Path(marker).exists():
                return True
        except OSError:
            continue
    return False


def loopback_routing_enabled() -> bool:
    raw = (os.environ.get(ROUTE_ENV) or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return running_in_container()


def docker_host_alias() -> str:
    """Return the validated Docker host alias ('' disables routing)."""
    configured = os.environ.get(ALIAS_ENV)
    if configured is None:
        configured = os.environ.get(_ANSIBLE_ALIAS_ENV)
    alias = DEFAULT_DOCKER_HOST_ALIAS if configured is None else configured.strip()
    if alias and not _HOST_ALIAS_RE.fullmatch(alias):
        logger.warning("Ignoring invalid Docker host alias {!r}", alias)
        return ""
    return alias


def is_loopback_host(host: str | None) -> bool:
    normalized = str(host or "").strip().strip("[]").rstrip(".").lower()
    if not normalized:
        return False
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return normalized == "localhost" or normalized.endswith(".localhost")


def route_loopback_host(host: str, *, force: bool = False, purpose: str = "connection") -> str:
    """Return the Docker host alias for loopback ``host`` when routing applies.

    ``force=True`` skips the container check (used when the connection is made
    from a separate bridge-network container, e.g. the agent command runner).
    """
    if not is_loopback_host(host):
        return host
    if not (force or loopback_routing_enabled()):
        return host
    alias = docker_host_alias()
    if not alias or is_loopback_host(alias):
        return host
    route_key = (purpose, str(host), alias)
    if route_key in _LOGGED_ROUTES:
        logger.debug("Routing loopback {} target {} -> {} (Docker host)", purpose, host, alias)
    else:
        _LOGGED_ROUTES.add(route_key)
        logger.info("Routing loopback {} target {} -> {} (Docker host)", purpose, host, alias)
    return alias


def route_loopback_url(url: str, *, force: bool = False, purpose: str = "http") -> str:
    """Rewrite the host of a loopback URL to the Docker host alias when routing applies."""
    raw = str(url or "")
    if not raw or "://" not in raw:
        return raw
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return raw
    routed = route_loopback_host(hostname, force=force, purpose=purpose)
    if routed == hostname:
        return raw
    userinfo, _, _hostport = parsed.netloc.rpartition("@")
    netloc = f"{userinfo}@" if userinfo else ""
    netloc += routed
    if port is not None:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
