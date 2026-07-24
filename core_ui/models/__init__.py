"""
Core UI models: app-level permissions, chat sessions, managed secrets, and shared preferences.

F-08a.10: pure-move package split. Public import path stays ``core_ui.models``.
Submodules keep each responsibility under 500 lines without schema changes.
"""

from .access import (
    DEFAULT_ALLOWED_FEATURES,
    EXPLICIT_OPT_IN_FEATURES,
    FEATURE_CHOICES,
    STAFF_ONLY_FEATURES,
    GroupAppPermission,
    UserAppPermission,
)
from .audit import LLMUsageLog, UserActivityLog
from .chat import (
    AssistantAction,
    ChatArtifact,
    ChatMessage,
    ChatSession,
    ChatTurnState,
)
from .preferences import DashboardLayout, TerminalPreference
from .secrets import ManagedSecret

__all__ = [
    "FEATURE_CHOICES",
    "DEFAULT_ALLOWED_FEATURES",
    "EXPLICIT_OPT_IN_FEATURES",
    "STAFF_ONLY_FEATURES",
    "ChatSession",
    "ChatMessage",
    "AssistantAction",
    "ChatTurnState",
    "ChatArtifact",
    "UserAppPermission",
    "GroupAppPermission",
    "UserActivityLog",
    "LLMUsageLog",
    "ManagedSecret",
    "TerminalPreference",
    "DashboardLayout",
]
