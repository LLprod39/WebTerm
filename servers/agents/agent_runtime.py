"""
In-process registry for live agent engine instances.

HTTP views and WebSocket consumers use this registry to deliver control
signals (stop/pause/resume/reply) to the currently running engine.
"""

from __future__ import annotations

from threading import RLock
from typing import Any

from asgiref.sync import sync_to_async

from core_ui.services.ai_execution_context import abuild_execution_context
from servers.models_agents import AgentRun

_LOCK = RLock()
_ENGINES_BY_RUN_ID: dict[int, Any] = {}
_RUN_IDS_BY_AGENT_ID: dict[int, int] = {}
DEFAULT_RUNTIME_CONTROL = {
    "stop_requested": False,
    "pause_requested": False,
    "reply_nonce": 0,
    "reply_ack_nonce": 0,
    "reply_text": "",
}


def execution_binding_snapshot(context: Any | None) -> dict[str, Any]:
    binding = getattr(context, "binding", None)
    return binding.to_dict() if binding is not None else {}


def execution_mode_value(context: Any | None) -> str:
    mode = getattr(context, "mode", None)
    return str(getattr(mode, "value", None) or "interactive")


async def build_agent_execution_context(engine: Any, purpose: str, *, surface: str):
    engine._provider_invocation_seq += 1
    state: dict[str, Any] = {}
    run_record = engine.run_record
    if run_record is not None and run_record.pk:
        state = await sync_to_async(
            lambda: AgentRun.objects.filter(pk=run_record.pk)
            .values(
                "provider_binding_snapshot",
                "provider_session_id",
                "provider_execution_mode",
            )
            .get(),
            thread_sensitive=True,
        )()
    base_binding = state.get("provider_binding_snapshot") or execution_binding_snapshot(engine.execution_context)
    run_id = getattr(run_record, "pk", None)
    return await abuild_execution_context(
        actor_user_id=getattr(engine.user, "pk", None),
        project_id=getattr(engine.agent, "project_id", None),
        purpose=purpose,
        source_kind="agent_run",
        source_id=run_id or f"ephemeral-{id(engine)}",
        mode=state.get("provider_execution_mode") or "interactive",
        stored_binding=base_binding,
        requested_provider=engine.model_preference,
        requested_specific_model=engine.specific_model,
        provider_session_id=state.get("provider_session_id") or "",
        idempotency_key=f"agent:{run_id}:llm:{engine._provider_invocation_seq}" if run_id else "",
        tool_policy={"surface": surface, "webtrerm_tools_only": True},
    )


def build_runtime_control_state(raw: Any | None = None) -> dict[str, Any]:
    control = dict(DEFAULT_RUNTIME_CONTROL)
    if not isinstance(raw, dict):
        return control

    control["stop_requested"] = bool(raw.get("stop_requested"))
    control["pause_requested"] = bool(raw.get("pause_requested"))

    for key in ("reply_nonce", "reply_ack_nonce"):
        try:
            control[key] = max(0, int(raw.get(key) or 0))
        except (TypeError, ValueError):
            control[key] = 0

    reply_text = raw.get("reply_text", "")
    control["reply_text"] = str(reply_text or "")
    return control


def reset_runtime_control_state() -> dict[str, Any]:
    return dict(DEFAULT_RUNTIME_CONTROL)


def is_runtime_stop_requested(run_or_control: AgentRun | dict[str, Any] | None) -> bool:
    raw = getattr(run_or_control, "runtime_control", run_or_control)
    control = build_runtime_control_state(raw)
    return bool(control["stop_requested"])


def update_runtime_control(
    run: AgentRun,
    *,
    live_engine: Any | None = None,
    stop_requested: bool | None = None,
    pause_requested: bool | None = None,
    reply_text: str | None = None,
    reply_ack_nonce: int | None = None,
) -> tuple[dict[str, Any], bool]:
    control = build_runtime_control_state(getattr(run, "runtime_control", None))

    if stop_requested is not None:
        control["stop_requested"] = bool(stop_requested)
    if pause_requested is not None:
        control["pause_requested"] = bool(pause_requested)
    if reply_text is not None:
        control["reply_nonce"] = int(control["reply_nonce"]) + 1
        control["reply_text"] = str(reply_text)

    reply_delivered = False
    if live_engine is not None:
        if stop_requested is True:
            live_engine.request_stop()
        if pause_requested is True:
            live_engine.request_pause()
        elif pause_requested is False:
            live_engine.request_resume()
        if reply_text is not None and live_engine.provide_user_reply(str(reply_text)):
            control["reply_ack_nonce"] = int(control["reply_nonce"])
            control["reply_text"] = ""
            reply_delivered = True

    if reply_ack_nonce is not None:
        ack = max(int(control["reply_ack_nonce"]), int(reply_ack_nonce))
        control["reply_ack_nonce"] = ack
        if ack >= int(control["reply_nonce"]):
            control["reply_text"] = ""

    run.runtime_control = control
    run.save(update_fields=["runtime_control"])
    return control, reply_delivered


def register_engine(run_id: int, agent_id: int | None, engine: Any) -> None:
    run_id = int(run_id)
    with _LOCK:
        _ENGINES_BY_RUN_ID[run_id] = engine
        if agent_id is not None:
            _RUN_IDS_BY_AGENT_ID[int(agent_id)] = run_id


def unregister_engine(run_id: int, engine: Any | None = None) -> None:
    run_id = int(run_id)
    with _LOCK:
        current = _ENGINES_BY_RUN_ID.get(run_id)
        if current is None:
            return
        if engine is not None and current is not engine:
            return

        _ENGINES_BY_RUN_ID.pop(run_id, None)

        for agent_id, mapped_run_id in list(_RUN_IDS_BY_AGENT_ID.items()):
            if mapped_run_id == run_id:
                _RUN_IDS_BY_AGENT_ID.pop(agent_id, None)


def clear_registered_engines() -> None:
    """Clear in-process live-engine registrations for tests and process lifecycle resets."""
    with _LOCK:
        _ENGINES_BY_RUN_ID.clear()
        _RUN_IDS_BY_AGENT_ID.clear()


def get_engine_for_run(run_id: int) -> Any | None:
    with _LOCK:
        return _ENGINES_BY_RUN_ID.get(int(run_id))


def get_engine_for_agent(agent_id: int) -> Any | None:
    with _LOCK:
        run_id = _RUN_IDS_BY_AGENT_ID.get(int(agent_id))
        if run_id is None:
            return None
        return _ENGINES_BY_RUN_ID.get(run_id)
