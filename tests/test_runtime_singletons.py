from __future__ import annotations

from app.core.provider_registry import (
    ProviderRegistry,
    get_provider_registry,
    reset_provider_registry,
    set_provider_registry,
)
from servers.agents.agent_runtime import (
    clear_registered_engines,
    get_engine_for_agent,
    get_engine_for_run,
    register_engine,
    unregister_engine,
)
from studio.executor.registry import (
    clear_node_registry,
    get_node_registry,
    restore_node_registry,
    snapshot_node_registry,
)


class _DummyNode:
    node_type = "test/dummy"

    def __init__(self, node_id: str, node_data: dict) -> None:
        self.node_id = node_id
        self.node_data = node_data


def test_provider_registry_can_be_installed_and_reset():
    reset_provider_registry()
    custom_registry = ProviderRegistry()

    try:
        set_provider_registry(custom_registry)
        assert get_provider_registry() is custom_registry

        reset_provider_registry()
        fresh_registry = get_provider_registry()
        assert fresh_registry is not custom_registry
        assert isinstance(fresh_registry, ProviderRegistry)
    finally:
        reset_provider_registry()


def test_unregister_engine_clears_agent_mapping_without_engine_agent_attr():
    clear_registered_engines()
    engine = object()

    register_engine(run_id=101, agent_id=202, engine=engine)
    assert get_engine_for_run(101) is engine
    assert get_engine_for_agent(202) is engine

    unregister_engine(run_id=101, engine=engine)

    assert get_engine_for_run(101) is None
    assert get_engine_for_agent(202) is None


def test_clear_registered_engines_removes_all_live_engine_mappings():
    clear_registered_engines()
    first_engine = object()
    second_engine = object()

    register_engine(run_id=1, agent_id=10, engine=first_engine)
    register_engine(run_id=2, agent_id=20, engine=second_engine)

    clear_registered_engines()

    assert get_engine_for_run(1) is None
    assert get_engine_for_run(2) is None
    assert get_engine_for_agent(10) is None
    assert get_engine_for_agent(20) is None


def test_studio_node_registry_can_be_snapshot_cleared_and_restored():
    node_registry = get_node_registry()
    original = snapshot_node_registry()

    try:
        clear_node_registry()
        assert node_registry.list_types() == []

        node_registry.register(_DummyNode)
        created = node_registry.create("test/dummy", node_id="n1", node_data={"x": 1})

        assert node_registry.list_types() == ["test/dummy"]
        assert isinstance(created, _DummyNode)
        assert created.node_id == "n1"
        assert created.node_data == {"x": 1}
    finally:
        restore_node_registry(original)

    assert snapshot_node_registry() == original
