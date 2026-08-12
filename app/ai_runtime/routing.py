"""Deterministic provider route selection with fail-closed semantics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .contracts import ProviderBinding
from .errors import ProviderRouteUnavailableError


class ProviderRouteSource(StrEnum):
    EXPLICIT = "explicit"
    STORED = "stored"
    USER_DEFAULT = "user_default"
    WORKSPACE_DEFAULT = "workspace_default"


@dataclass(frozen=True, slots=True)
class ResolvedProviderRoute:
    binding: ProviderBinding
    source: ProviderRouteSource


AccessDecision = bool | tuple[bool, str]
AccessChecker = Callable[[ProviderBinding], AccessDecision]


def resolve_provider_route(
    *,
    explicit: ProviderBinding | None = None,
    stored: ProviderBinding | None = None,
    user_default: ProviderBinding | None = None,
    workspace_default: ProviderBinding | None = None,
    can_use: AccessChecker | None = None,
) -> ResolvedProviderRoute:
    """Select exactly one route by precedence and never try a fallback.

    If the highest-precedence configured binding is denied or unavailable, the
    request fails. This prevents an unexpected account or billing path switch.
    """
    selected: tuple[ProviderRouteSource, ProviderBinding] | None = None
    for source, binding in (
        (ProviderRouteSource.EXPLICIT, explicit),
        (ProviderRouteSource.STORED, stored),
        (ProviderRouteSource.USER_DEFAULT, user_default),
        (ProviderRouteSource.WORKSPACE_DEFAULT, workspace_default),
    ):
        if binding is not None:
            selected = (source, binding)
            break

    if selected is None:
        raise ProviderRouteUnavailableError("No provider binding is configured")

    source, binding = selected
    if can_use is not None:
        decision = can_use(binding)
        allowed, reason = decision if isinstance(decision, tuple) else (decision, "binding is not allowed")
        if not allowed:
            raise ProviderRouteUnavailableError(
                "Selected provider binding is unavailable",
                details={"source": source.value, "target_id": binding.target_id, "reason": reason},
            )

    return ResolvedProviderRoute(binding=binding, source=source)
