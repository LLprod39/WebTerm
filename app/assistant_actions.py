from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class AssistantActionError(Exception):
    def __init__(self, message: str, *, status: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or {}


@dataclass(frozen=True)
class AssistantActionContext:
    user: Any
    input_payload: dict[str, Any]
    request: Any | None = None
    source: str = "assistant_chat"


AssistantActionHandler = Callable[[AssistantActionContext], dict[str, Any]]
AssistantRuntimeContextProvider = Callable[[Any], dict[str, Any]]


@dataclass(frozen=True)
class AssistantActionSpec:
    action_type: str
    label: str
    description: str
    required_feature: str
    risk: str = "read"
    requires_confirmation: bool = False
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: AssistantActionHandler | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "label": self.label,
            "description": self.description,
            "required_feature": self.required_feature,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "input_schema": self.input_schema,
        }


_registry: dict[str, AssistantActionSpec] = {}
_runtime_context_providers: dict[str, AssistantRuntimeContextProvider] = {}


def register_action(spec: AssistantActionSpec) -> None:
    if not spec.action_type:
        raise ValueError("Assistant action type is required")
    existing = _registry.get(spec.action_type)
    if existing and existing != spec:
        raise ValueError(f"Assistant action already registered: {spec.action_type}")
    _registry[spec.action_type] = spec


def get_action_spec(action_type: str) -> AssistantActionSpec | None:
    return _registry.get(str(action_type or "").strip())


def list_action_specs() -> list[AssistantActionSpec]:
    return [spec for _key, spec in sorted(_registry.items())]


def reset_action_registry() -> None:
    _registry.clear()


def register_runtime_context_provider(name: str, provider: AssistantRuntimeContextProvider) -> None:
    key = str(name or "").strip()
    if not key:
        raise ValueError("Assistant runtime context provider name is required")
    _runtime_context_providers[key] = provider


def build_runtime_context(user: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "agents": [],
        "servers": [],
        "pipelines": [],
        "selection_rules": [
            "Use ids from this snapshot when the name match is exact or unique.",
            "Ask a clarification when several objects match the same operator phrase.",
            "Never infer secrets or credentials from names.",
        ],
    }
    for name, provider in sorted(_runtime_context_providers.items()):
        try:
            payload = provider(user)
        except Exception as exc:  # noqa: BLE001 - context is best-effort for chat planning.
            logger.debug("assistant runtime context provider %s skipped: %s", name, exc)
            continue
        if isinstance(payload, dict):
            context.update(payload)
    return context


def reset_runtime_context_providers() -> None:
    _runtime_context_providers.clear()
