from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMUsageEvent:
    provider: str
    model_name: str
    input_text: str
    output_text: str
    duration_ms: int
    status: str = "success"
    purpose: str = ""
    metadata: dict[str, Any] | None = None
    audit_context: Mapping[str, Any] = field(default_factory=dict)


LLMUsageContextProvider = Callable[[], Mapping[str, Any]]
LLMUsageRecorder = Callable[[LLMUsageEvent], None]

_llm_usage_context_provider: LLMUsageContextProvider | None = None
_llm_usage_recorder: LLMUsageRecorder | None = None


def register_llm_usage_context_provider(provider: LLMUsageContextProvider | None) -> None:
    """Register the app-level provider for request/audit context snapshots."""
    global _llm_usage_context_provider
    _llm_usage_context_provider = provider


def register_llm_usage_recorder(recorder: LLMUsageRecorder | None) -> None:
    """Register the app-level persistence sink for LLM usage events."""
    global _llm_usage_recorder
    _llm_usage_recorder = recorder


def capture_llm_usage_context() -> dict[str, Any]:
    if _llm_usage_context_provider is None:
        return {}
    return dict(_llm_usage_context_provider() or {})


def record_llm_usage_event(event: LLMUsageEvent) -> bool:
    if _llm_usage_recorder is None:
        return False
    _llm_usage_recorder(event)
    return True
