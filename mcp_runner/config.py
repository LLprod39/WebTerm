"""Runner configuration and the environment passlist for spawned MCP processes."""

from __future__ import annotations

import os

# System environment variables forwarded to a spawned MCP process. Everything
# else in the Runner's own os.environ (its auth token, unrelated secrets) is
# dropped; the per-server env and managed secrets arrive explicitly in the spec.
ENV_PASSLIST_DEFAULTS: tuple[str, ...] = (
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
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
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
    # npm/uv caches so npx/uvx do not re-download on every cold start.
    "NPM_CONFIG_CACHE",
    "npm_config_cache",
    "UV_CACHE_DIR",
    "XDG_CACHE_HOME",
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(part.strip() for part in raw.replace(";", ",").replace(" ", ",").split(",") if part.strip())


class RunnerConfig:
    def __init__(self) -> None:
        self.token = os.getenv("MCP_RUNNER_TOKEN", "").strip()
        self.session_ttl_seconds = max(_env_int("MCP_RUNNER_SESSION_TTL_SECONDS", 300), 30)
        self.max_sessions = max(_env_int("MCP_RUNNER_MAX_SESSIONS", 50), 1)
        self.reap_interval_seconds = max(_env_int("MCP_RUNNER_REAP_INTERVAL_SECONDS", 30), 5)
        self.initialize_timeout_seconds = max(_env_int("MCP_RUNNER_INITIALIZE_TIMEOUT_SECONDS", 20), 1)
        self.request_timeout_seconds = max(_env_int("MCP_RUNNER_REQUEST_TIMEOUT_SECONDS", 120), 1)
        self.terminate_timeout_seconds = max(_env_int("MCP_RUNNER_TERMINATE_TIMEOUT_SECONDS", 3), 1)
        self.env_passlist = set(ENV_PASSLIST_DEFAULTS) | set(_env_list("MCP_RUNNER_ENV_PASSLIST"))

    def validate_startup(self) -> None:
        """Reject a runner process that would expose its execution API anonymously."""
        if not self.token:
            raise RuntimeError("MCP_RUNNER_TOKEN is required; refusing to start without authentication")

    def build_child_env(self, spec_env: dict | None) -> dict[str, str]:
        env: dict[str, str] = {}
        for key, value in os.environ.items():
            if key in self.env_passlist or key.startswith("LC_"):
                env[key] = value
        for key, value in (spec_env or {}).items():
            if str(key).strip():
                env[str(key)] = str(value)
        return env
