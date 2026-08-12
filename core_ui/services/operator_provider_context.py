"""Provider-binding helpers for the durable operator chat loop."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from asgiref.sync import sync_to_async

from core_ui.services.ai_execution_context import (
    abuild_execution_context,
    active_project_for_execution,
    build_execution_context,
)


def prepare_operator_turn_context(*, session: Any, user: Any, provider_binding: dict[str, Any] | None):
    project = active_project_for_execution(user)
    context = build_execution_context(
        actor_user_id=user.pk,
        project_id=project.pk if project else None,
        purpose="orchestrator",
        source_kind="chat_session",
        source_id=session.pk,
        explicit_binding=provider_binding,
        stored_binding=session.provider_binding,
        requested_provider="auto",
        provider_session_id=session.provider_session_id,
    )
    binding = context.binding.to_dict()
    old_identity = _binding_identity(session.provider_binding)
    new_identity = _binding_identity(binding)
    update_fields: list[str] = []
    if session.provider_binding != binding:
        session.provider_binding = binding
        update_fields.append("provider_binding")
    if old_identity != new_identity and session.provider_session_id:
        session.provider_session_id = ""
        context = replace(context, provider_session_id="")
        update_fields.append("provider_session_id")
    if update_fields:
        session.save(update_fields=[*update_fields, "updated_at"])
    return context


async def build_operator_iteration_context(*, session: Any, turn: Any, user: Any, iteration: int):
    state = await sync_to_async(
        lambda: type(session).objects.filter(pk=session.pk).values("provider_binding", "provider_session_id").get(),
        thread_sensitive=True,
    )()
    project_id = await sync_to_async(
        lambda: getattr(active_project_for_execution(user), "pk", None),
        thread_sensitive=True,
    )()
    return await abuild_execution_context(
        actor_user_id=user.pk,
        project_id=project_id,
        purpose="orchestrator",
        source_kind="chat_session",
        source_id=session.pk,
        stored_binding=state["provider_binding"] or turn.provider_binding_snapshot,
        requested_provider="auto",
        # An empty durable session id is authoritative: falling back to the turn
        # snapshot would resurrect a session belonging to an earlier connection.
        provider_session_id=state["provider_session_id"],
        idempotency_key=f"chat:{session.pk}:turn:{turn.pk}:iteration:{iteration}",
        tool_policy={"surface": "assistant", "webtrerm_tools_only": True},
    )


def _binding_identity(binding: dict[str, Any] | None) -> tuple[Any, ...]:
    value = binding or {}
    return (
        value.get("target_id"),
        value.get("connection_id"),
        value.get("pool_id"),
        value.get("selected_connection_id"),
    )
