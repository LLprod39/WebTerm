"""
servers/consumers — WebSocket consumer package.

Structure:
  ssh_terminal.py   — SSHTerminalConsumer (SSH + AI chat + SFTP)
  rdp_terminal.py   — RDPTerminalConsumer (Guacamole/RDP proxy)
  agent_live.py     — AgentLiveConsumer   (live agent run events)

servers/routing.py imports from here. All original module paths
(servers.consumers, servers.rdp_consumer, servers.agent_consumer)
are kept as backward-compatible re-export shims.
"""
from servers.consumers.agent_live import AgentLiveConsumer
from servers.consumers.rdp_terminal import RDPTerminalConsumer
from servers.consumers.ssh_terminal import SSHTerminalConsumer

__all__ = [
    "SSHTerminalConsumer",
    "RDPTerminalConsumer",
    "AgentLiveConsumer",
]
