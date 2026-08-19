from types import SimpleNamespace

from studio.model_policy import sanitize_pipeline_nodes_for_user


def test_non_admin_pipeline_nodes_inherit_workspace_model_without_mutating_input():
    user = SimpleNamespace(is_staff=False, is_superuser=False)
    nodes = [
        {"id": "agent", "type": "agent/react", "data": {"provider": "grok", "model": "grok-3"}},
        {"id": "output", "type": "output/text", "data": {"value": "ok"}},
    ]

    sanitized = sanitize_pipeline_nodes_for_user(user, nodes)

    assert sanitized[0]["data"]["provider"] == "auto"
    assert sanitized[0]["data"]["model"] == ""
    assert sanitized[1] == nodes[1]
    assert nodes[0]["data"] == {"provider": "grok", "model": "grok-3"}


def test_admin_pipeline_nodes_keep_explicit_model():
    user = SimpleNamespace(is_staff=True, is_superuser=False)
    nodes = [{"id": "agent", "type": "agent/react", "data": {"provider": "grok", "model": "grok-3"}}]

    assert sanitize_pipeline_nodes_for_user(user, nodes) is nodes
