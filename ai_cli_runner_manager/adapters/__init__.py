"""Provider adapters executed only inside ephemeral CLI runner containers."""

from .codex import CodexSubscriptionAdapter
from .grok import GrokSubscriptionAdapter

__all__ = ["CodexSubscriptionAdapter", "GrokSubscriptionAdapter"]
