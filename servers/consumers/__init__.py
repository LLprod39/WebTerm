"""
servers/consumers — WebSocket consumer package.

Structure:
  ssh_terminal.py   — SSHTerminalConsumer (SSH + AI chat + SFTP)
  agent_live.py     — AgentLiveConsumer   (live agent run events)

servers/routing.py imports from here. All original module paths
(servers.consumers, servers.agent_consumer)
are kept as backward-compatible re-export shims.
"""
from servers.consumers.agent_live import AgentLiveConsumer
from servers.consumers.monitoring_live import MonitoringLiveConsumer
from servers.consumers.ssh_terminal import SSHTerminalConsumer

__all__ = [
    "SSHTerminalConsumer",
    "AgentLiveConsumer",
    "MonitoringLiveConsumer",
]
