"""Execution-context helpers for Studio assistant and pipeline nodes."""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async

from app.ai_runtime import ProviderBinding
from core_ui.ai_model_policy import stored_operational_provider_binding, user_can_manage_ai_routing
from core_ui.services.ai_execution_context import (
    abuild_execution_context,
    binding_from_payload,
    platform_default_binding,
)


def explicit_binding_from_node(
    config: dict[str, Any],
    *,
    purpose: str,
    inherited_binding: dict[str, Any] | None = None,
) -> ProviderBinding | None:
    payload = config.get("provider_binding")
    if payload not in (None, {}, ""):
        return binding_from_payload(payload)
    if inherited_binding:
        return binding_from_payload(inherited_binding)
    provider = str(config.get("provider") or "").strip()
    if provider and provider != "auto":
        return platform_default_binding(
            purpose=purpose,
            requested_provider=provider,
            requested_specific_model=str(config.get("model") or "").strip() or None,
        )
    return None


async def build_pipeline_execution_context(
    run: Any,
    *,
    purpose: str,
    node_id: str,
    config: dict[str, Any] | None = None,
    inherited_binding: dict[str, Any] | None = None,
):
    state = await sync_to_async(
        lambda: (
            type(run)
            .objects.filter(pk=run.pk)
            .values(
                "pipeline__owner_id",
                "triggered_by_id",
                "project_id",
                "provider_binding_snapshot",
                "provider_session_id",
                "provider_execution_mode",
            )
            .get()
        ),
        thread_sensitive=True,
    )()
    from django.contrib.auth import get_user_model

    actor_user_id = state["triggered_by_id"] or state["pipeline__owner_id"]
    actor = await sync_to_async(
        lambda: get_user_model().objects.get(pk=actor_user_id),
        thread_sensitive=True,
    )()
    can_manage_routing = await sync_to_async(user_can_manage_ai_routing, thread_sensitive=True)(actor)
    stored_binding = await sync_to_async(stored_operational_provider_binding, thread_sensitive=True)(
        actor,
        state["provider_binding_snapshot"],
    )
    explicit = (
        explicit_binding_from_node(
            dict(config or {}),
            purpose=purpose,
            inherited_binding=inherited_binding,
        )
        if can_manage_routing
        else None
    )
    return await abuild_execution_context(
        actor_user_id=actor_user_id,
        project_id=state["project_id"],
        purpose=purpose,
        source_kind="pipeline_run",
        source_id=run.pk,
        mode=state["provider_execution_mode"],
        explicit_binding=explicit,
        stored_binding=stored_binding,
        requested_provider="auto",
        allow_user_preference=can_manage_routing,
        provider_session_id=state["provider_session_id"],
        idempotency_key=f"pipeline:{run.pk}:node:{node_id}:purpose:{purpose}",
        tool_policy={"surface": "studio", "node_id": node_id, "webtrerm_tools_only": True},
    )
