"""Provider-neutral contracts for WebTerm LLM execution.

This package intentionally has no Django dependency. Delivery and persistence
layers may depend on it, while the shared runtime remains reusable by workers
and the isolated CLI runner manager.
"""

from .contracts import (
    ExecutionMode,
    LLMExecutionContext,
    ProviderBinding,
    ProviderEventType,
    ProviderEventV1,
)
from .errors import ProviderRouteUnavailableError, ProviderRuntimeError
from .routing import ProviderRouteSource, ResolvedProviderRoute, resolve_provider_route
from .targets import (
    CANONICAL_PROVIDER_TARGETS,
    SUBSCRIPTION_PROVIDER_TARGETS,
    ProviderTarget,
    canonicalize_target_id,
    is_subscription_target,
    legacy_runtime_provider_id,
)

__all__ = [
    "CANONICAL_PROVIDER_TARGETS",
    "SUBSCRIPTION_PROVIDER_TARGETS",
    "ExecutionMode",
    "LLMExecutionContext",
    "ProviderBinding",
    "ProviderEventType",
    "ProviderEventV1",
    "ProviderRouteSource",
    "ProviderRouteUnavailableError",
    "ProviderRuntimeError",
    "ProviderTarget",
    "ResolvedProviderRoute",
    "canonicalize_target_id",
    "is_subscription_target",
    "legacy_runtime_provider_id",
    "resolve_provider_route",
]
