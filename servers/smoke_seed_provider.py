from __future__ import annotations

from asgiref.sync import async_to_sync

from app.smoke_seed_provider import SmokeSeedItem, SmokeSshTarget
from servers.models import Server, ServerAgent
from servers.secret_utils import store_server_auth_secret
from servers.ssh_host_keys import enroll_server_host_key


class DjangoSmokeServerSeedProvider:
    def upsert_server(self, *, user_id: int, index: int, target: SmokeSshTarget) -> SmokeSeedItem:
        server_name = f"Smoke SSH {index:02d}"
        server, _created = Server.objects.get_or_create(
            user_id=user_id,
            name=server_name,
            defaults={
                "host": target.host,
                "port": target.port,
                "username": target.username,
                "auth_method": "password",
                "server_type": "ssh",
                "is_active": True,
            },
        )
        server.host = target.host
        server.port = target.port
        server.username = target.username
        server.auth_method = "password"
        server.server_type = "ssh"
        server.is_active = True
        server.ai_read_only = False
        server.trusted_host_keys = []
        server.save()
        store_server_auth_secret(server, secret_value=target.password)
        server.save()
        if target.host_key_fingerprint:
            async_to_sync(enroll_server_host_key)(
                server,
                expected_fingerprint=target.host_key_fingerprint,
                allow_replace=True,
            )
        return SmokeSeedItem(id=server.id, name=server.name)

    def upsert_agent(self, *, user_id: int, index: int, username: str, server_id: int) -> SmokeSeedItem:
        agent_name = f"Smoke Agent {index:02d}"
        commands = [f"sleep 1; printf 'AGENT_OK {username}\\n'; whoami"]
        agent, _created = ServerAgent.objects.get_or_create(
            user_id=user_id,
            name=agent_name,
            defaults={
                "mode": ServerAgent.MODE_MINI,
                "agent_type": ServerAgent.TYPE_CUSTOM,
                "commands": commands,
                "ai_prompt": "Smoke agent for concurrent runtime checks",
                "is_enabled": True,
            },
        )
        agent.mode = ServerAgent.MODE_MINI
        agent.agent_type = ServerAgent.TYPE_CUSTOM
        agent.commands = commands
        agent.ai_prompt = "Smoke agent for concurrent runtime checks"
        agent.is_enabled = True
        agent.save()
        agent.servers.set([server_id])
        return SmokeSeedItem(id=agent.id, name=agent.name)
