"""Regression coverage for the terminal AI provider-state model import."""

from servers.models import TerminalAiProviderState
from servers.models_inventory import TerminalAiProviderState as InventoryTerminalAiProviderState


def test_provider_state_is_exported_from_public_models_module():
    assert TerminalAiProviderState is InventoryTerminalAiProviderState
