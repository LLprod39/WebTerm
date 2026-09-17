"""Classify isolated agent-command failures: control plane vs SSH vs command."""

from __future__ import annotations

import os
from typing import Any

KIND_CONTROL_PLANE = "control_plane"
KIND_SSH = "ssh"
KIND_COMMAND = "command"

CONTROL_PLANE_MARKERS = (
    "docker.sock",
    "cannot connect to the docker daemon",
    "permission denied while trying to connect to the docker",
    "connect to the docker api",
    "error during connect",
    "docker proxy",
    "agent command runner image",
    "must be an immutable",
    "ephemeral agent command runner failed",
    "ephemeral agent command runner timed out",
    "agent command runner request exceeds",
    "invalid response",
    "unsupported response",
    "docker: permission denied",
    "permission denied while trying to connect to the docker api",
    "control_plane",
    "канал выполнения",
    "нет доступа к docker",
)

SSH_MARKERS = (
    "trusted ssh host keys",
    "permission denied (publickey",
    "permission denied (password",
    "authentication failed",
    "host key",
    "ssh connection",
    "connect failed",
    "connection reset by peer",
    "connection timed out",
    "no route to host",
    "network is unreachable",
    "banner exchange",
    "login timeout",
)


class AgentCommandRuntimeError(RuntimeError):
    """The isolated command runner could not safely execute the request."""

    def __init__(self, message: str, *, kind: str = KIND_CONTROL_PLANE):
        super().__init__(message)
        self.kind = kind if kind in {KIND_CONTROL_PLANE, KIND_SSH, KIND_COMMAND} else KIND_CONTROL_PLANE


def docker_socket_gid_label() -> str:
    value = str(os.environ.get("DOCKER_SOCKET_GID") or "").strip()
    return value or "не задан (compose default 0)"


def classify_agent_runtime_detail(detail: Any) -> str:
    text = str(detail or "").strip().lower()
    if not text:
        return KIND_CONTROL_PLANE
    if _has_control_plane_marker(text):
        return KIND_CONTROL_PLANE
    if any(marker in text for marker in SSH_MARKERS):
        return KIND_SSH
    return KIND_CONTROL_PLANE


def _has_control_plane_marker(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in CONTROL_PLANE_MARKERS):
        return True
    return "docker" in lowered and "permission denied" in lowered


def is_control_plane_text(detail: Any) -> bool:
    return _has_control_plane_marker(str(detail or ""))


def format_control_plane_message(detail: str = "") -> str:
    snippet = " ".join(str(detail or "").split())[:280]
    suffix = f" Детали: {snippet}" if snippet else ""
    return (
        "CONTROL_PLANE: канал выполнения на хосте WebTerm недоступен (Docker API). "
        "Команды на целевом сервере не запускались, SSH до цели не проверялся. "
        f"DOCKER_SOCKET_GID={docker_socket_gid_label()}.{suffix} "
        "Выставьте DOCKER_SOCKET_GID (gid владельца /var/run/docker.sock) и пересоздайте agent-execution."
    )


def format_ssh_message(detail: str = "") -> str:
    snippet = " ".join(str(detail or "").split())[:280]
    suffix = f" Детали: {snippet}" if snippet else ""
    return f"SSH: не удалось подключиться к целевому серверу.{suffix}"


def format_runtime_error(kind: str, detail: str = "") -> str:
    if kind == KIND_SSH:
        return format_ssh_message(detail)
    if kind == KIND_COMMAND:
        snippet = " ".join(str(detail or "").split())[:280]
        return snippet or "Команда на сервере завершилась с ошибкой."
    return format_control_plane_message(detail)


def error_from_runner_failure(detail: str, *, default_kind: str = KIND_CONTROL_PLANE) -> AgentCommandRuntimeError:
    kind = classify_agent_runtime_detail(detail)
    if kind == KIND_CONTROL_PLANE and default_kind == KIND_SSH and not is_control_plane_text(detail):
        kind = KIND_SSH
    message = format_runtime_error(kind, detail)
    return AgentCommandRuntimeError(message, kind=kind)
