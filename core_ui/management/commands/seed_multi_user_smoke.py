from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core_ui.models import UserAppPermission
from servers.models import Server, ServerAgent
from servers.secret_utils import store_server_auth_secret
from studio.models import Pipeline


class Command(BaseCommand):
    help = "Seed reproducible users/servers/pipelines for isolated multi-user smoke tests."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=4)
        parser.add_argument("--password", default="SmokePass123!")
        parser.add_argument("--ssh-host", default="ssh-target")
        parser.add_argument("--ssh-port", type=int, default=2222)
        parser.add_argument("--ssh-username", default="smoke")
        parser.add_argument("--ssh-password", default="smoke-password")
        parser.add_argument("--prefix", default="smoke-user")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        users_count = max(int(options["users"] or 1), 1)
        password = str(options["password"] or "SmokePass123!")
        ssh_host = str(options["ssh_host"] or "ssh-target").strip() or "ssh-target"
        ssh_port = int(options["ssh_port"] or 2222)
        ssh_username = str(options["ssh_username"] or "smoke").strip() or "smoke"
        ssh_password = str(options["ssh_password"] or "smoke-password")
        prefix = str(options["prefix"] or "smoke-user").strip() or "smoke-user"

        payload: dict[str, object] = {
            "password": password,
            "ssh_target": {
                "host": ssh_host,
                "port": ssh_port,
                "username": ssh_username,
                "password": ssh_password,
            },
            "users": [],
        }

        for index in range(1, users_count + 1):
            username = f"{prefix}-{index:02d}"
            email = f"{username}@example.test"
            user, _created = User.objects.get_or_create(
                username=username,
                defaults={"email": email, "is_active": True},
            )
            user.email = email
            user.is_active = True
            user.is_staff = False
            user.is_superuser = False
            user.set_password(password)
            user.save()

            for feature in ("servers", "studio", "agents"):
                UserAppPermission.objects.update_or_create(
                    user=user,
                    feature=feature,
                    defaults={"allowed": True},
                )

            server_name = f"Smoke SSH {index:02d}"
            server, _server_created = Server.objects.get_or_create(
                user=user,
                name=server_name,
                defaults={
                    "host": ssh_host,
                    "port": ssh_port,
                    "username": ssh_username,
                    "auth_method": "password",
                    "server_type": "ssh",
                    "is_active": True,
                },
            )
            server.host = ssh_host
            server.port = ssh_port
            server.username = ssh_username
            server.auth_method = "password"
            server.server_type = "ssh"
            server.is_active = True
            server.trusted_host_keys = []
            server.save()
            store_server_auth_secret(server, secret_value=ssh_password)
            server.save()

            pipeline_name = f"Smoke Pipeline {index:02d}"
            nodes = [
                {
                    "id": "manual",
                    "type": "trigger/manual",
                    "position": {"x": 0, "y": 0},
                    "data": {"label": "Manual trigger"},
                },
                {
                    "id": "ssh",
                    "type": "agent/ssh_cmd",
                    "position": {"x": 280, "y": 0},
                    "data": {
                        "label": "Smoke SSH command",
                        "server_id": server.id,
                        "command": "printf 'PIPELINE_OK {load_user} {run_index}\\n'; whoami",
                    },
                },
            ]
            edges = [
                {
                    "id": "edge-manual-ssh",
                    "source": "manual",
                    "target": "ssh",
                }
            ]
            pipeline, _pipeline_created = Pipeline.objects.get_or_create(
                owner=user,
                name=pipeline_name,
                defaults={
                    "description": "Isolated smoke pipeline for concurrent runtime checks",
                    "nodes": nodes,
                    "edges": edges,
                },
            )
            pipeline.description = "Isolated smoke pipeline for concurrent runtime checks"
            pipeline.nodes = nodes
            pipeline.edges = edges
            pipeline.save()
            pipeline.sync_triggers_from_nodes()

            agent_name = f"Smoke Agent {index:02d}"
            agent, _agent_created = ServerAgent.objects.get_or_create(
                user=user,
                name=agent_name,
                defaults={
                    "mode": ServerAgent.MODE_MINI,
                    "agent_type": ServerAgent.TYPE_CUSTOM,
                    "commands": [f"sleep 1; printf 'AGENT_OK {username}\\n'; whoami"],
                    "ai_prompt": "Smoke agent for concurrent runtime checks",
                    "is_enabled": True,
                },
            )
            agent.mode = ServerAgent.MODE_MINI
            agent.agent_type = ServerAgent.TYPE_CUSTOM
            agent.commands = [f"sleep 1; printf 'AGENT_OK {username}\\n'; whoami"]
            agent.ai_prompt = "Smoke agent for concurrent runtime checks"
            agent.is_enabled = True
            agent.save()
            agent.servers.set([server])

            payload["users"].append(
                {
                    "username": username,
                    "server_id": server.id,
                    "pipeline_id": pipeline.id,
                    "agent_id": agent.id,
                    "server_name": server.name,
                    "pipeline_name": pipeline.name,
                    "agent_name": agent.name,
                }
            )

        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if options["json"]:
            self.stdout.write(text)
            return

        self.stdout.write(f"Seeded {users_count} smoke users")
        self.stdout.write(text)
