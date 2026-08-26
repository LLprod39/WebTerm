"""Bounded versioned request protocol between WebTerm and CLI runners."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.ai_runtime import ProviderEventType, ProviderEventV1, ProviderTarget, canonicalize_target_id

_CONNECTION_REF = re.compile(r"^[a-z0-9][a-z0-9_-]{7,79}$")
_INVOCATION_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{7,159}$")
_MAX_MESSAGES = 200
_MAX_TOOLS = 200
_MAX_TEXT_CHARS = 500_000
_REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}


class RunnerProtocolError(ValueError):
    pass


class RunnerAction(StrEnum):
    AUTH_START = "auth_start"
    AUTH_STATUS = "auth_status"
    VERIFY = "verify"
    RUN = "run"


@dataclass(frozen=True, slots=True)
class RunnerRequestV1:
    action: RunnerAction
    connection_ref: str
    target_id: str
    invocation_id: str
    model_id: str | None = None
    reasoning_effort: str | None = None
    provider_session_id: str | None = None
    system_prompt: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_policy: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    idempotency_key: str = ""
    schema: str = "webterm.ai-cli-runner-request.v1"

    def __post_init__(self) -> None:
        if self.schema != "webterm.ai-cli-runner-request.v1":
            raise RunnerProtocolError("Unsupported runner request schema")
        if not isinstance(self.action, RunnerAction):
            object.__setattr__(self, "action", RunnerAction(self.action))
        connection_ref = self.connection_ref.strip().lower()
        if not _CONNECTION_REF.fullmatch(connection_ref):
            raise RunnerProtocolError("connection_ref has an invalid format")
        object.__setattr__(self, "connection_ref", connection_ref)
        if not _INVOCATION_REF.fullmatch(self.invocation_id):
            raise RunnerProtocolError("invocation_id has an invalid format")
        target_id = canonicalize_target_id(self.target_id)
        if target_id not in {
            ProviderTarget.CODEX_SUBSCRIPTION.value,
            ProviderTarget.GROK_SUBSCRIPTION.value,
        }:
            raise RunnerProtocolError("Runner accepts only subscription targets")
        object.__setattr__(self, "target_id", target_id)
        if len(self.messages) > _MAX_MESSAGES or len(self.tools) > _MAX_TOOLS:
            raise RunnerProtocolError("Runner request has too many messages or tools")
        text_chars = len(self.system_prompt or "") + sum(
            len(str(message.get("content") or "")) for message in self.messages
        )
        if text_chars > _MAX_TEXT_CHARS:
            raise RunnerProtocolError("Runner request text exceeds the 500000 character limit")
        if self.reasoning_effort is not None:
            reasoning_effort = self.reasoning_effort.strip().lower()
            if reasoning_effort not in _REASONING_EFFORTS:
                raise RunnerProtocolError("reasoning_effort is not supported")
            object.__setattr__(self, "reasoning_effort", reasoning_effort)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RunnerRequestV1:
        if not isinstance(value, dict):
            raise RunnerProtocolError("Runner request must be a JSON object")
        try:
            return cls(
                schema=str(value.get("schema") or ""),
                action=RunnerAction(value.get("action")),
                connection_ref=str(value.get("connection_ref") or ""),
                target_id=str(value.get("target_id") or ""),
                invocation_id=str(value.get("invocation_id") or ""),
                model_id=_optional_string(value.get("model_id")),
                reasoning_effort=_optional_string(value.get("reasoning_effort")),
                provider_session_id=_optional_string(value.get("provider_session_id")),
                system_prompt=_optional_string(value.get("system_prompt")),
                messages=_dict_list(value.get("messages"), "messages"),
                tools=_dict_list(value.get("tools"), "tools"),
                tool_policy=_dict(value.get("tool_policy"), "tool_policy"),
                output_schema=_optional_dict(value.get("output_schema"), "output_schema"),
                idempotency_key=str(value.get("idempotency_key") or ""),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, RunnerProtocolError):
                raise
            raise RunnerProtocolError("Runner request contains an invalid field") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "action": self.action.value,
            "connection_ref": self.connection_ref,
            "target_id": self.target_id,
            "invocation_id": self.invocation_id,
            "model_id": self.model_id,
            "reasoning_effort": self.reasoning_effort,
            "provider_session_id": self.provider_session_id,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "tools": self.tools,
            "tool_policy": self.tool_policy,
            "output_schema": self.output_schema,
            "idempotency_key": self.idempotency_key,
        }


def error_event(code: str, message: str, *, retryable: bool = False) -> ProviderEventV1:
    return ProviderEventV1(
        ProviderEventType.ERROR,
        {"code": code, "message": message, "retryable": retryable},
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RunnerProtocolError("Expected a string field")
    return value


def _dict_list(value: Any, name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RunnerProtocolError(f"{name} must be a list of objects")
    return value


def _dict(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RunnerProtocolError(f"{name} must be an object")
    return value


def _optional_dict(value: Any, name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    return _dict(value, name)
