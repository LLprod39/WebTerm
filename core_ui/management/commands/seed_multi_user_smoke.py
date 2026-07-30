from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from app.smoke_seed_provider import (
    SmokeSshTarget,
    upsert_smoke_agent,
    upsert_smoke_pipeline,
    upsert_smoke_server,
)
from core_ui.models import UserAppPermission


class Command(BaseCommand):
    help = "Seed reproducible users/servers/pipelines for isolated multi-user smoke tests."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=4)
        parser.add_argument("--password", default="SmokePass123!")
        parser.add_argument("--ssh-host", default="ssh-target")
        parser.add_argument("--ssh-port", type=int, default=2222)
        parser.add_argument("--ssh-username", default="smoke")
        parser.add_argument("--ssh-password", default="smoke-password")
        parser.add_argument("--ssh-host-key-fingerprint", default="")
        parser.add_argument("--prefix", default="smoke-user")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        users_count = max(int(options["users"] or 1), 1)
        password = str(options["password"] or "SmokePass123!")
        ssh_host = str(options["ssh_host"] or "ssh-target").strip() or "ssh-target"
        ssh_port = int(options["ssh_port"] or 2222)
        ssh_username = str(options["ssh_username"] or "smoke").strip() or "smoke"
        ssh_password = str(options["ssh_password"] or "smoke-password")
        ssh_host_key_fingerprint = str(options["ssh_host_key_fingerprint"] or "").strip()
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
        target = SmokeSshTarget(
            host=ssh_host,
            port=ssh_port,
            username=ssh_username,
            password=ssh_password,
            host_key_fingerprint=ssh_host_key_fingerprint,
        )

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

            server = upsert_smoke_server(user_id=user.id, index=index, target=target)
            pipeline = upsert_smoke_pipeline(user_id=user.id, index=index, server_id=server.id)
            agent = upsert_smoke_agent(user_id=user.id, index=index, username=username, server_id=server.id)

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
