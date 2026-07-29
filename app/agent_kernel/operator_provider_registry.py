"""
app/agent_kernel/operator_provider_registry.py

Global registry for the OperatorServersProvider implementation.

Lives in the shared ``app/`` layer so that ``core_ui.*`` (the Operator UI and
session layer) can reach ``servers.*`` behaviour without importing servers
directly. This satisfies the import-linter contract
``core_ui must not import servers`` (see ``.importlinter`` contract 5).

Lifecycle:
  1. ``servers.apps.ServersConfig.ready()`` calls
     ``register(ServersOperatorProvider())``.
  2. The ``core_ui`` operator services call the module-level helpers below,
     which delegate to the registered provider.

Kept Django-free (contract 1: ``app.agent_kernel`` must not import Django), so
querysets and model instances cross the boundary typed as ``Any`` — exactly the
convention already used by ``skill_provider_registry`` and the other
``app/agent_kernel`` service locators.
"""

from __future__ import annotations

from typing import Any, Protocol


class OperatorServersProvider(Protocol):
    """What the Operator layer needs from ``servers`` behind an app-level port."""

    def accessible_servers_queryset(self, user: Any) -> Any: ...

    def owned_servers_queryset(self, user: Any) -> Any: ...

    def server_names_for_ids(self, ids: list[int]) -> list[str]: ...

    def get_agent_run(self, run_id: int) -> Any | None: ...

    def get_playbook_run(self, run_id: int) -> Any | None: ...

    def build_agent_run_report_response(self, run: Any) -> dict[str, Any]: ...

    def memory_overview(self, server_id: int) -> dict[str, Any]: ...

    def ingest_operator_lesson(
        self,
        *,
        server_id: int,
        title: str,
        body: str,
        actor_user_id: int | None,
        chat_id: int | None,
        importance: float,
        run_dream: bool,
    ) -> dict[str, Any]: ...

    def collect_duty_facts(self, user: Any, *, include_agent_runs: bool, since_hours: int = 16) -> dict[str, Any]: ...

    def prefer_resolve_server_for_message(
        self, arguments: dict[str, Any], *, user_message: str
    ) -> dict[str, Any] | None: ...

    def prepare_list_servers_arguments(self, arguments: dict[str, Any], *, user_message: str) -> dict[str, Any]: ...


_registry: OperatorServersProvider | None = None


def register(provider: OperatorServersProvider) -> None:
    global _registry
    _registry = provider


def get() -> OperatorServersProvider | None:
    return _registry


def _require() -> OperatorServersProvider:
    provider = _registry
    if provider is None:
        raise RuntimeError("Operator servers provider is not registered (servers app not ready).")
    return provider


# ── Module-level helpers: the surface the core_ui operator services call ──────


def accessible_servers_queryset(user: Any) -> Any:
    return _require().accessible_servers_queryset(user)


def owned_servers_queryset(user: Any) -> Any:
    return _require().owned_servers_queryset(user)


def server_names_for_ids(ids: list[int]) -> list[str]:
    return _require().server_names_for_ids(ids)


def get_agent_run(run_id: int) -> Any | None:
    return _require().get_agent_run(run_id)


def get_playbook_run(run_id: int) -> Any | None:
    return _require().get_playbook_run(run_id)


def build_agent_run_report_response(run: Any) -> dict[str, Any]:
    return _require().build_agent_run_report_response(run)


def memory_overview(server_id: int) -> dict[str, Any]:
    return _require().memory_overview(server_id)


def ingest_operator_lesson(
    *,
    server_id: int,
    title: str,
    body: str,
    actor_user_id: int | None,
    chat_id: int | None,
    importance: float,
    run_dream: bool,
) -> dict[str, Any]:
    return _require().ingest_operator_lesson(
        server_id=server_id,
        title=title,
        body=body,
        actor_user_id=actor_user_id,
        chat_id=chat_id,
        importance=importance,
        run_dream=run_dream,
    )


def collect_duty_facts(user: Any, *, include_agent_runs: bool, since_hours: int = 16) -> dict[str, Any]:
    return _require().collect_duty_facts(user, include_agent_runs=include_agent_runs, since_hours=since_hours)


def prefer_resolve_server_for_message(arguments: dict[str, Any], *, user_message: str) -> dict[str, Any] | None:
    return _require().prefer_resolve_server_for_message(arguments, user_message=user_message)


def prepare_list_servers_arguments(arguments: dict[str, Any], *, user_message: str) -> dict[str, Any]:
    return _require().prepare_list_servers_arguments(arguments, user_message=user_message)
