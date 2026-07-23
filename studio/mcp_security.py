from __future__ import annotations

import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings

from studio.models import MCPServerPool


@dataclass(frozen=True)
class MCPStdioPolicyResult:
    allowed: bool
    error: str = ""


# Environment variables safe to forward to an MCP subprocess. Anything outside
# this passlist (Django secret key, managed-secret master key, provider API
# keys, DB credentials, ...) is deliberately dropped so a third-party MCP server
# never inherits platform secrets from os.environ.
_ENV_PASSLIST_DEFAULTS: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LANGUAGE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "USER",
    "LOGNAME",
    "SHELL",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    # Proxy / TLS trust so `npx`, `uvx`, pip, etc. can still reach the network
    # through a corporate proxy and validate certificates.
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "FTP_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "ftp_proxy",
    "no_proxy",
    "NODE_EXTRA_CA_CERTS",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)


def _setting_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = getattr(settings, name, os.getenv(name, ",".join(default)))
    items = re.split(r"[,;\s]+", raw) if isinstance(raw, str) else list(raw or [])
    return tuple(str(item).strip().lower() for item in items if str(item).strip())


def _setting_list_cased(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Like _setting_list but preserves case (env var names are case-sensitive)."""
    raw = getattr(settings, name, os.getenv(name, ",".join(default)))
    items = re.split(r"[,;\s]+", raw) if isinstance(raw, str) else list(raw or [])
    return tuple(str(item).strip() for item in items if str(item).strip())


def _setting_bool(name: str, default: bool) -> bool:
    raw = getattr(settings, name, os.getenv(name, default))
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _command_name(command: str) -> str:
    name = re.split(r"[\\/]+", str(command or "").strip())[-1].lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def _runner_configured() -> bool:
    """True when the MCP Runner service is wired up, so stdio MCP runs isolated
    in the Runner rather than as a subprocess on the backend host."""
    raw = getattr(settings, "STUDIO_MCP_RUNNER_URL", os.getenv("STUDIO_MCP_RUNNER_URL", ""))
    return bool(str(raw or "").strip())


def build_mcp_subprocess_env(
    extra_env: dict | None = None,
    secret_env: dict | None = None,
) -> dict[str, str]:
    """Build a minimal, passlisted environment for an MCP stdio subprocess.

    The child only receives passlisted system variables plus the server's own
    declared env and managed secrets — never the full platform os.environ.
    """
    allowed = set(_ENV_PASSLIST_DEFAULTS)
    allowed.update(_setting_list_cased("STUDIO_MCP_ENV_PASSLIST", ()))
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in allowed or key.startswith("LC_"):
            env[key] = value
    for source in (extra_env or {}, secret_env or {}):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if str(key).strip():
                env[str(key)] = str(value)
    return env


def validate_stdio_mcp_policy(
    command: str,
    args: list | None = None,
    *,
    user=None,
    action: str = "run",
) -> MCPStdioPolicyResult:
    # With the Runner wired up, stdio MCP runs isolated from the backend host, so
    # it is safe to enable by default and open to non-admins. Without it, stdio
    # spawns on the host, so it stays off / admin-only unless explicitly enabled.
    runner = _runner_configured()
    if not _setting_bool("STUDIO_MCP_STDIO_ENABLED", runner or bool(getattr(settings, "DEBUG", False))):
        return MCPStdioPolicyResult(
            False,
            "Stdio MCP servers are disabled on this deployment.",
        )
    if (
        user is not None
        and _setting_bool("STUDIO_MCP_STDIO_ADMIN_ONLY", not runner)
        and not bool(getattr(user, "is_staff", False))
    ):
        return MCPStdioPolicyResult(
            False,
            f"Only admins can {action} stdio MCP servers.",
        )
    command_name = _command_name(command)
    if not command_name:
        return MCPStdioPolicyResult(False, "Stdio MCP command is required.")
    allowed_commands = _setting_list("STUDIO_MCP_STDIO_ALLOWED_COMMANDS", ("npx", "node", "python", "python3"))
    if allowed_commands and command_name not in allowed_commands:
        return MCPStdioPolicyResult(
            False,
            f"Stdio MCP command '{command_name}' is not allowed.",
        )
    # An allowlisted interpreter is still an arbitrary-code vector via inline-exec
    # flags (`python -c`, `node -e`, ...). Force MCP servers to be shipped as a
    # script or package instead of inline source pasted into args.
    denied_flags = _setting_list("STUDIO_MCP_STDIO_DENIED_ARGS", ("-c", "-e", "--eval", "--exec", "--command"))
    if args and denied_flags:
        for raw_arg in args:
            flag = str(raw_arg).strip().lower().split("=", 1)[0]
            if flag in denied_flags:
                return MCPStdioPolicyResult(
                    False,
                    f"Stdio MCP inline-code flag '{flag}' is not allowed; ship a script or package instead.",
                )
    return MCPStdioPolicyResult(True)


def _host_is_private(host: str) -> bool:
    candidates: list[ipaddress._BaseAddress] = []
    try:
        candidates.append(ipaddress.ip_address(host))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            # Unresolvable host cannot reach an internal service either; let the
            # connection itself fail rather than guess.
            return False
        for info in infos:
            raw = str(info[4][0]).split("%", 1)[0]
            try:
                candidates.append(ipaddress.ip_address(raw))
            except ValueError:
                continue
    for ip in candidates:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        ):
            return True
    return False


def validate_sse_mcp_policy(url: str, *, user=None, action: str = "run") -> MCPStdioPolicyResult:
    raw = (url or "").strip()
    if not raw:
        return MCPStdioPolicyResult(False, "MCP URL is required.")
    parsed = urlparse(raw if "://" in raw else "http://" + raw)
    if parsed.scheme not in ("http", "https"):
        return MCPStdioPolicyResult(False, "MCP URL must use http or https.")
    host = parsed.hostname
    if not host:
        return MCPStdioPolicyResult(False, "MCP URL host is required.")
    # Admins may target internal endpoints (bundled keycloak/demo MCP, docker
    # service names). Non-admins must not point an MCP at private/loopback
    # addresses, which would turn "test connection" into an internal-network
    # SSRF probe.
    if user is not None and bool(getattr(user, "is_staff", False)):
        return MCPStdioPolicyResult(True)
    if _setting_bool("STUDIO_MCP_SSE_ALLOW_PRIVATE", False):
        return MCPStdioPolicyResult(True)
    if _host_is_private(host):
        return MCPStdioPolicyResult(
            False,
            f"Only admins can {action} an MCP server pointing at a private or loopback address.",
        )
    return MCPStdioPolicyResult(True)


def validate_mcp_runtime_policy(mcp: MCPServerPool, *, user=None, action: str = "run") -> MCPStdioPolicyResult:
    if mcp.transport != MCPServerPool.TRANSPORT_STDIO:
        return MCPStdioPolicyResult(True)
    return validate_stdio_mcp_policy(mcp.command, mcp.args, user=user, action=action)
