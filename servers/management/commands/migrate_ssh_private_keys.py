from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from servers.models_inventory import Server
from servers.secret_utils import get_server_auth_secret
from servers.ssh_private_keys import (
    get_server_private_key_text,
    is_managed_private_key_path,
    is_managed_private_key_reference,
    managed_private_keys_root,
    resolve_managed_private_key_path,
    store_uploaded_private_key,
)


class Command(BaseCommand):
    help = "Migrate WebTerm-owned plaintext SSH private-key files into encrypted ManagedSecret records."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist encrypted records, update Server.key_path, and remove migrated plaintext files.",
        )

    def handle(self, *args, **options) -> None:
        apply = bool(options["apply"])
        counts = {
            "migrated": 0,
            "would_migrate": 0,
            "already_managed": 0,
            "external": 0,
            "orphan_plaintext": 0,
            "orphans_removed": 0,
            "failed": 0,
        }

        servers = Server.objects.filter(auth_method__in=["key", "key_password"]).exclude(key_path="").order_by("id")
        for server in servers.iterator():
            key_reference = str(server.key_path or "").strip()
            if is_managed_private_key_reference(key_reference, server_id=server.id):
                try:
                    get_server_private_key_text(server)
                except Exception as exc:
                    counts["failed"] += 1
                    self.stderr.write(f"server_id={server.id}: managed key verification failed: {type(exc).__name__}")
                else:
                    counts["already_managed"] += 1
                continue

            if not is_managed_private_key_path(key_reference):
                counts["external"] += 1
                continue

            try:
                private_key = get_server_private_key_text(server)
                passphrase = get_server_auth_secret(server) if server.auth_method == "key_password" else ""
                if not apply:
                    counts["would_migrate"] += 1
                    continue

                legacy_path = resolve_managed_private_key_path(key_reference)
                if legacy_path is None:
                    raise ValueError("legacy managed key path cannot be resolved")
                with transaction.atomic():
                    managed_reference = store_uploaded_private_key(server, private_key, passphrase=passphrase)
                    Server.objects.filter(pk=server.pk).update(key_path=managed_reference)

                legacy_path.unlink(missing_ok=True)
                if legacy_path.exists():
                    raise OSError("legacy key file still exists after cleanup")
                counts["migrated"] += 1
            except Exception as exc:
                counts["failed"] += 1
                self.stderr.write(f"server_id={server.id}: migration failed: {type(exc).__name__}")

        referenced_paths = {
            path
            for raw_path in Server.objects.exclude(key_path="").values_list("key_path", flat=True)
            if (path := resolve_managed_private_key_path(str(raw_path or ""))) is not None
        }
        key_root = managed_private_keys_root()
        if key_root.exists():
            for orphan_path in key_root.rglob("*.key"):
                if orphan_path.resolve() in referenced_paths:
                    continue
                counts["orphan_plaintext"] += 1
                if not apply:
                    continue
                try:
                    orphan_path.unlink()
                    counts["orphans_removed"] += 1
                except OSError as exc:
                    counts["failed"] += 1
                    self.stderr.write(f"orphan key cleanup failed: {type(exc).__name__}")

        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        self.stdout.write(summary)
        if counts["failed"]:
            raise CommandError("One or more SSH private keys could not be migrated safely")
