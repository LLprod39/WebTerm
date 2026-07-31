from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from servers.encryption import PasswordEncryption
from servers.models import Server
from servers.secret_utils import (
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
        master_password = str(options["master_password"] or "").strip()
        apply = bool(options["apply"])
        clear_legacy = bool(options["clear_legacy"])
        if clear_legacy and not apply:
            raise CommandError("--clear-legacy requires --apply")
        servers = Server.objects.filter(
            Q(encrypted_password__gt="")
            | Q(salt__isnull=False)
            | Q(encrypted_sudo_password__gt="")
            | Q(sudo_salt__isnull=False)
        ).order_by("id")
        migrated = 0
        skipped = 0
        failed = 0
        cleared = 0

        for server in servers:
            updates: list[tuple[str, str]] = []
            existing: list[str] = []
            try:
                if server.encrypted_password:
                    if has_managed_server_secret(server):
                        existing.append("auth")
                    else:
                        if not master_password:
                            raise CommandError("--master-password is required for legacy auth ciphertext")
                        if not server.salt:
                            raise CommandError("legacy auth ciphertext has no salt")
                        updates.append(
                            (
                                "auth",
                                PasswordEncryption.decrypt_password(
                                    server.encrypted_password,
                                    master_password,
                                    bytes(server.salt),
                                ),
                            )
                        )
                if server.encrypted_sudo_password:
                    if has_managed_server_sudo_secret(server):
                        existing.append("sudo")
                    else:
                        if not master_password:
                            raise CommandError("--master-password is required for legacy sudo ciphertext")
                        if not server.sudo_salt:
                            raise CommandError("legacy sudo ciphertext has no salt")
                        updates.append(
                            (
                                "sudo",
                                PasswordEncryption.decrypt_password(
                                    server.encrypted_sudo_password,
                                    master_password,
                                    bytes(server.sudo_salt),
                                ),
                            )
                        )
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"[failed] {server.id} {server.name}: {exc}"))
                continue

            if not updates and not clear_legacy:
                skipped += 1
                kinds = ",".join(existing) or "legacy metadata only"
                self.stdout.write(f"[skip] {server.id} {server.name}: {kinds}")
                continue

            if apply:
                with transaction.atomic():
                    for kind, secret in updates:
                        if kind == "auth":
                            store_server_auth_secret(server, secret_value=secret)
                        else:
                            store_server_sudo_secret(server, secret_value=secret)
                    if clear_legacy:
                        Server.objects.filter(pk=server.pk).update(
                            encrypted_password="",
                            salt=None,
                            encrypted_sudo_password="",
                            sudo_salt=None,
                        )
                        cleared += 1
            if updates:
                migrated += 1
            mode = "migrated" if apply else "would migrate"
            kinds = ",".join(kind for kind, _secret in updates)
            suffix = "; legacy cleared" if apply and clear_legacy else ""
            self.stdout.write(self.style.SUCCESS(f"[{mode}] {server.id} {server.name}: {kinds or 'managed'}{suffix}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. apply={apply} clear_legacy={clear_legacy} migrated={migrated} "
                f"cleared={cleared} skipped={skipped} failed={failed}"
            )
        )
        if failed:
            raise CommandError(f"Legacy secret migration failed for {failed} server(s)")
