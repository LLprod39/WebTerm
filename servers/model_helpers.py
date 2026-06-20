from __future__ import annotations

from typing import Any


def server_network_context_summary(corporate_context: str, network_config: dict[str, Any] | None) -> str:
    parts = []
    if corporate_context:
        parts.append(corporate_context.strip())

    if network_config:
        if network_config.get("proxy", {}).get("http_proxy"):
            parts.append(f"Прокси: {network_config['proxy']['http_proxy']}")
        if network_config.get("vpn", {}).get("required"):
            vpn_type = network_config["vpn"].get("type", "VPN")
            parts.append(f"VPN: {vpn_type}")
        if network_config.get("network", {}).get("bastion_host"):
            parts.append(f"Bastion: {network_config['network']['bastion_host']}")
        if network_config.get("firewall", {}).get("inbound_ports"):
            ports = network_config["firewall"]["inbound_ports"]
            parts.append(f"Порты: {','.join(map(str, ports))}")

    return "\n".join(parts) if parts else "Стандартная сеть"


def update_server_network_flags(server: Any) -> None:
    if not server.network_config:
        return

    network_config = server.network_config
    server.has_proxy = bool(network_config.get("proxy", {}).get("http_proxy"))
    server.requires_vpn = bool(network_config.get("vpn", {}).get("required"))
    if network_config.get("firewall"):
        server.behind_firewall = True
