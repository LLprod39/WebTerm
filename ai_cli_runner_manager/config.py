"""Fail-closed runner-manager configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_IMMUTABLE_IMAGE = re.compile(r"^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RunnerManagerConfig:
    token: str
    codex_runner_image: str = ""
    grok_runner_image: str = ""
    credential_volume_prefix: str = "webterm-ai-cli-cred-"
    docker_command: str = "docker"
    docker_network: str = "webterm-ai-cli-egress"
    egress_proxy_url: str = "http://ai-cli-egress-proxy:3128"
    cpus: str = "1.0"
    memory: str = "1g"
    pids_limit: int = 128
    request_timeout_seconds: int = 900
    output_limit_bytes: int = 2 * 1024 * 1024
    fake_runtime: bool = False

    @classmethod
    def from_env(cls) -> RunnerManagerConfig:
        return cls(
            token=os.getenv("AI_CLI_RUNNER_MANAGER_TOKEN", "").strip(),
            codex_runner_image=os.getenv("AI_CLI_CODEX_RUNNER_IMAGE", "").strip(),
            grok_runner_image=os.getenv("AI_CLI_GROK_RUNNER_IMAGE", "").strip(),
            credential_volume_prefix=os.getenv("AI_CLI_CREDENTIAL_VOLUME_PREFIX", "webterm-ai-cli-cred-").strip(),
            docker_command=os.getenv("AI_CLI_DOCKER_COMMAND", "docker").strip() or "docker",
            docker_network=os.getenv("AI_CLI_DOCKER_NETWORK", "webterm-ai-cli-egress").strip(),
            egress_proxy_url=os.getenv("AI_CLI_EGRESS_PROXY_URL", "http://ai-cli-egress-proxy:3128").strip(),
            cpus=os.getenv("AI_CLI_DOCKER_CPUS", "1.0").strip(),
            memory=os.getenv("AI_CLI_DOCKER_MEMORY", "1g").strip(),
            pids_limit=int(os.getenv("AI_CLI_DOCKER_PIDS_LIMIT", "128")),
            request_timeout_seconds=int(os.getenv("AI_CLI_REQUEST_TIMEOUT_SECONDS", "900")),
            output_limit_bytes=int(os.getenv("AI_CLI_OUTPUT_LIMIT_BYTES", str(2 * 1024 * 1024))),
            fake_runtime=os.getenv("AI_CLI_RUNNER_FAKE", "").strip().lower() in {"1", "true", "yes"},
        )

    def validate_startup(self) -> None:
        if not self.token:
            raise RuntimeError("AI_CLI_RUNNER_MANAGER_TOKEN is required")
        if not self.fake_runtime and not _IMMUTABLE_IMAGE.fullmatch(self.codex_runner_image):
            raise RuntimeError("AI_CLI_CODEX_RUNNER_IMAGE must be an immutable image digest")
        if not self.fake_runtime and not _IMMUTABLE_IMAGE.fullmatch(self.grok_runner_image):
            raise RuntimeError("AI_CLI_GROK_RUNNER_IMAGE must be an immutable image digest")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{3,63}", self.credential_volume_prefix):
            raise RuntimeError("AI_CLI_CREDENTIAL_VOLUME_PREFIX has an invalid format")
        if not self.docker_network or self.docker_network in {"host", "none", "bridge"}:
            raise RuntimeError("AI_CLI_DOCKER_NETWORK must be a dedicated egress-controlled network")
        if not re.fullmatch(r"http://[a-z0-9][a-z0-9.-]*:[0-9]{2,5}", self.egress_proxy_url):
            raise RuntimeError("AI_CLI_EGRESS_PROXY_URL must be an internal HTTP proxy URL without credentials")
        if self.pids_limit < 1 or self.pids_limit > 256:
            raise RuntimeError("AI_CLI_DOCKER_PIDS_LIMIT must be between 1 and 256")
        if self.request_timeout_seconds < 1 or self.request_timeout_seconds > 3600:
            raise RuntimeError("AI_CLI_REQUEST_TIMEOUT_SECONDS must be between 1 and 3600")
        if self.output_limit_bytes < 1024 or self.output_limit_bytes > 10 * 1024 * 1024:
            raise RuntimeError("AI_CLI_OUTPUT_LIMIT_BYTES must be between 1 KiB and 10 MiB")

    def runner_image_for(self, target_id: str) -> str:
        if target_id == "codex_subscription":
            return self.codex_runner_image
        if target_id == "grok_subscription":
            return self.grok_runner_image
        raise RuntimeError("Unsupported subscription runner target")
