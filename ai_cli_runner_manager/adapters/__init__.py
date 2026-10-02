"""Provider adapters executed only inside ephemeral CLI runner containers."""

from .antigravity import AntigravitySubscriptionAdapter
from .codex import CodexSubscriptionAdapter
from .cursor import CursorSubscriptionAdapter
from .grok import GrokSubscriptionAdapter

__all__ = [
    "AntigravitySubscriptionAdapter",
    "CodexSubscriptionAdapter",
    "CursorSubscriptionAdapter",
    "GrokSubscriptionAdapter",
]
