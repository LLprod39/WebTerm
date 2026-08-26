"""Versioned provider bindings, execution context, and stream events."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from .targets import canonicalize_target_id


class ExecutionMode(StrEnum):
    INTERACTIVE = "interactive"
    UNATTENDED = "unattended"


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    target_id: str
    connection_id: int | None = None
    pool_id: int | None = None
    model_id: str | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_id", canonicalize_target_id(self.target_id))
        if self.connection_id is not None and self.pool_id is not None:
            raise ValueError("Provider binding cannot select both connection_id and pool_id")
        if self.connection_id is not None and self.connection_id <= 0:
            raise ValueError("connection_id must be a positive integer")
        if self.pool_id is not None and self.pool_id <= 0:
            raise ValueError("pool_id must be a positive integer")
        if self.model_id is not None:
            model_id = self.model_id.strip()
            object.__setattr__(self, "model_id", model_id or None)
        if self.reasoning_effort is not None:
            reasoning_effort = self.reasoning_effort.strip().lower()
            object.__setattr__(self, "reasoning_effort", reasoning_effort or None)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ProviderBinding:
        return cls(
            target_id=value.get("target_id", ""),
            connection_id=value.get("connection_id"),
            pool_id=value.get("pool_id"),
            model_id=value.get("model_id"),
            reasoning_effort=value.get("reasoning_effort"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "connection_id": self.connection_id,
            "pool_id": self.pool_id,
            "model_id": self.model_id,
            "reasoning_effort": self.reasoning_effort,
        }


@dataclass(frozen=True, slots=True)
class LLMExecutionContext:
    actor_user_id: int | None
    project_id: int | None
    purpose: str
    source_kind: str
    source_id: str
    mode: ExecutionMode
    binding: ProviderBinding | None = None
    tool_policy: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    idempotency_key: str = ""
    provider_session_id: str = ""

    def __post_init__(self) -> None:
        if self.actor_user_id is not None and self.actor_user_id <= 0:
            raise ValueError("actor_user_id must be a positive integer")
        if self.project_id is not None and self.project_id <= 0:
            raise ValueError("project_id must be a positive integer")
        for field_name in ("purpose", "source_kind", "source_id"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, value)
        if not isinstance(self.mode, ExecutionMode):
            object.__setattr__(self, "mode", ExecutionMode(self.mode))
        object.__setattr__(self, "idempotency_key", self.idempotency_key.strip())
        object.__setattr__(self, "provider_session_id", self.provider_session_id.strip())

    def with_binding(self, binding: ProviderBinding) -> LLMExecutionContext:
        return replace(self, binding=binding)


class ProviderEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUIRED = "approval_required"
    USAGE = "usage"
    LIMIT = "limit"
    AUTH_REQUIRED = "auth_required"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ProviderEventV1:
    type: ProviderEventType
    payload: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self) -> None:
        if self.version != 1:
            raise ValueError("Only ProviderEventV1 version=1 is supported")
        if not isinstance(self.type, ProviderEventType):
            object.__setattr__(self, "type", ProviderEventType(self.type))

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version, "type": self.type.value, "payload": self.payload}
