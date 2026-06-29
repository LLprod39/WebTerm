from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from servers.models import Server
from servers.secret_utils import (
    get_server_auth_secret,
    get_server_sudo_secret,
    has_managed_server_secret,
    has_managed_server_sudo_secret,
    store_server_auth_secret,
    store_server_sudo_secret,
)


class Command(BaseCommand):
    help = "Migrate legacy MASTER_PASSWORD-encrypted server secrets into ManagedSecret."

    def add_arguments(self, parser):
        parser.add_argument("--master-password", default="", help="Legacy MASTER_PASSWORD used for decryption.")
        parser.add_argument("--apply", action="store_true", help="Write decrypted secrets into ManagedSecret.")
        parser.add_argument(
            "--clear-legacy",
            action="store_true",
            help="Clear encrypted legacy fields after a successful ManagedSecret write. Requires --apply.",
        )

    def handle(self, *args, **options):
        master_password = (options["master_password"] or os.getenv("MASTER_PASSWORD") or "").strip()
        apply = bool(options["apply"])
        clear_legacy = bool(options["clear_legacy"])
        if clear_legacy and not apply:
            raise CommandError("--clear-legacy requires --apply")
        if not master_password:
            raise CommandError("Set --master-password or MASTER_PASSWORD to decrypt legacy secrets.")

        servers = Server.objects.exclude(encrypted_password="") | Server.objects.exclude(encrypted_sudo_password="")
        seen: set[int] = set()
        migrated = 0
        skipped = 0
        failed = 0

        for server in servers.order_by("id"):
            if server.id in seen:
                continue
            seen.add(server.id)
            updates = []
            try:
                if server.encrypted_password and not has_managed_server_secret(server):
                    secret = get_server_auth_secret(server, master_password=master_password)
                    if not secret:
                        raise CommandError(f"Server {server.id}: decrypted auth secret is empty")
                    updates.append(("auth", secret))
                if server.encrypted_sudo_password and not has_managed_server_sudo_secret(server):
                    secret = get_server_sudo_secret(server, master_password=master_password)
                    if not secret:
                        raise CommandError(f"Server {server.id}: decrypted sudo secret is empty")
                    updates.append(("sudo", secret))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"[failed] {server.id} {server.name}: {exc}"))
                continue

            if not updates:
                skipped += 1
                self.stdout.write(f"[skip] {server.id} {server.name}: managed secret already exists")
                continue

            if apply:
                for kind, secret in updates:
                    if kind == "auth":
                        store_server_auth_secret(server, secret_value=secret)
                    else:
                        store_server_sudo_secret(server, secret_value=secret)
                if clear_legacy:
                    server.encrypted_password = ""
                    server.salt = None
                    server.encrypted_sudo_password = ""
                    server.sudo_salt = None
                    server.save(update_fields=["encrypted_password", "salt", "encrypted_sudo_password", "sudo_salt"])
                else:
                    server.save()
            migrated += 1
            mode = "migrated" if apply else "would migrate"
            kinds = ",".join(kind for kind, _secret in updates)
            self.stdout.write(self.style.SUCCESS(f"[{mode}] {server.id} {server.name}: {kinds}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. apply={apply} clear_legacy={clear_legacy} migrated={migrated} skipped={skipped} failed={failed}"
            )
        )
