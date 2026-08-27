"""Build fully resolved LLM execution contexts for WebTerm product surfaces."""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async

from app.ai_runtime import ExecutionMode, LLMExecutionContext, ProviderBinding
from app.ai_runtime.targets import canonicalize_target_id
from app.core.model_config import model_manager
from core_ui.projects import active_project_for_user
from core_ui.services.ai_provider_routing import resolve_execution_context


def binding_from_payload(value: Any) -> ProviderBinding | None:
    """Parse a persisted/API binding; an empty object means no override."""
    if value in (None, {}, ""):
        return None
    if not isinstance(value, dict):
        raise ValueError("provider_binding must be an object")
    return ProviderBinding.from_dict(value)


def platform_default_binding(
    *,
    purpose: str,
    requested_provider: str = "auto",
    requested_specific_model: str | None = None,
) -> ProviderBinding:
    """Represent the existing admin LLM configuration as a canonical binding.

    This is the lowest-precedence workspace route. It is an explicit configured
    target, not an error fallback; route failures never try another provider.
    """
    provider = str(requested_provider or "auto").strip().lower() or "auto"
    model_id = str(requested_specific_model or "").strip() or None
    if provider == "auto":
        provider, configured_model = model_manager.resolve_purpose(purpose)
        if model_id is None:
            model_id = str(configured_model or "").strip() or None
    return ProviderBinding(
        target_id=canonicalize_target_id(provider),
        model_id=model_id,
    )


def build_execution_context(
    *,
    actor_user_id: int | None,
    project_id: int | None,
    purpose: str,
    source_kind: str,
    source_id: str | int,
    mode: ExecutionMode | str = ExecutionMode.INTERACTIVE,
    explicit_binding: ProviderBinding | dict[str, Any] | None = None,
    stored_binding: ProviderBinding | dict[str, Any] | None = None,
    requested_provider: str = "auto",
    requested_specific_model: str | None = None,
    allow_user_preference: bool = True,
    provider_session_id: str = "",
    idempotency_key: str = "",
    tool_policy: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> LLMExecutionContext:
    """Resolve one binding with explicit/stored/user/workspace precedence."""
    explicit = (
        explicit_binding if isinstance(explicit_binding, ProviderBinding) else binding_from_payload(explicit_binding)
    )
    stored = stored_binding if isinstance(stored_binding, ProviderBinding) else binding_from_payload(stored_binding)
    context = LLMExecutionContext(
        actor_user_id=actor_user_id,
        project_id=project_id,
        purpose=purpose,
        source_kind=source_kind,
        source_id=str(source_id),
        mode=ExecutionMode(mode),
        binding=explicit,
        tool_policy=dict(tool_policy or {}),
        output_schema=output_schema,
        idempotency_key=idempotency_key,
        provider_session_id=provider_session_id,
    )
    return resolve_execution_context(
        context,
        explicit_binding=explicit,
        stored_binding=stored,
        platform_default=platform_default_binding(
            purpose=purpose,
            requested_provider=requested_provider,
            requested_specific_model=requested_specific_model,
        ),
        allow_user_preference=allow_user_preference,
    )


async def abuild_execution_context(**kwargs: Any) -> LLMExecutionContext:
    return await sync_to_async(build_execution_context, thread_sensitive=True)(**kwargs)


def active_project_for_execution(user):
    """Single dependency edge for product surfaces that need the active tenant."""
    return active_project_for_user(user)


def pin_binding_to_selected_connection(
    binding_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Convert a pool route snapshot into the exact selected connection route."""
    snapshot = dict(binding_snapshot or {})
    selected_connection_id = snapshot.pop("selected_connection_id", None)
    if selected_connection_id:
        snapshot["connection_id"] = selected_connection_id
        snapshot["pool_id"] = None
    return ProviderBinding.from_dict(snapshot).to_dict() if snapshot else {}
