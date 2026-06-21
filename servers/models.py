"""Compatibility exports for server models.

Django imports this module for model discovery. The concrete model classes live
in focused app-local modules and are imported here to preserve the public
``servers.models`` import path.
"""

from servers.models_agents import AgentRun, AgentRunDispatch, AgentRunEvent, ServerAgent
from servers.models_groups import (
    ServerGroup,
    ServerGroupMember,
    ServerGroupPermission,
    ServerGroupSubscription,
    ServerGroupTag,
)
from servers.models_inventory import (
    CommandSnapshot,
    Server,
    ServerCommandHistory,
    ServerConnection,
    ServerShare,
    TerminalAiChatMessage,
)
from servers.models_knowledge import GlobalServerRules, ServerGroupKnowledge, ServerKnowledge
from servers.models_memory import (
    ServerMemoryEpisode,
    ServerMemoryEvent,
    ServerMemoryPolicy,
    ServerMemoryRevalidation,
    ServerMemorySnapshot,
)
from servers.models_monitoring import (
    BackgroundWorkerState,
    ServerAlert,
    ServerHealthCheck,
    ServerWatcherDraft,
)

__all__ = [
    "AgentRun",
    "AgentRunDispatch",
    "AgentRunEvent",
    "BackgroundWorkerState",
    "CommandSnapshot",
    "GlobalServerRules",
    "Server",
    "ServerAgent",
    "ServerAlert",
    "ServerCommandHistory",
    "ServerConnection",
    "ServerGroup",
    "ServerGroupKnowledge",
    "ServerGroupMember",
    "ServerGroupPermission",
    "ServerGroupSubscription",
    "ServerGroupTag",
    "ServerHealthCheck",
    "ServerKnowledge",
    "ServerMemoryEpisode",
    "ServerMemoryEvent",
    "ServerMemoryPolicy",
    "ServerMemoryRevalidation",
    "ServerMemorySnapshot",
    "ServerShare",
    "ServerWatcherDraft",
    "TerminalAiChatMessage",
]
