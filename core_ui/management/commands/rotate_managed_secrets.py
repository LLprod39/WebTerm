from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core_ui.managed_secret_crypto import (
    ManagedSecretError,
    managed_secret_ciphertext_key_id,
    managed_secret_current_key_id,
    reencrypt_managed_secret,
)
from core_ui.managed_secrets import list_undecryptable_secrets
from core_ui.models import ManagedSecret


class Command(BaseCommand):
    help = "Re-encrypt all managed secrets with the configured current v2 key without exposing keys in argv."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument(
            "--expect-key-id",
            default="",
            help="Refuse rotation unless the configured current key id matches this value.",
        )

    def handle(self, *args, **options):
        batch_size = int(options["batch_size"] or 0)
        if batch_size < 1 or batch_size > 5000:
            raise CommandError("--batch-size must be between 1 and 5000")

        try:
            current_key_id = managed_secret_current_key_id()
        except ManagedSecretError as exc:
            raise CommandError(str(exc)) from exc
        expected_key_id = str(options["expect_key_id"] or "").strip()
        if expected_key_id and expected_key_id != current_key_id:
            raise CommandError(
                f"Configured managed secret key id is {current_key_id}, expected {expected_key_id}; refusing rotation"
            )

        broken = list_undecryptable_secrets(limit=None)
        if broken:
            sample = ", ".join(broken[:10])
            raise CommandError(
                f"Refusing rotation: {len(broken)} managed secrets are not decryptable with the configured keyring"
                f" ({sample})"
            )

        secret_ids = list(ManagedSecret.objects.order_by("id").values_list("id", flat=True))
        current_prefix = f"v2:{current_key_id}:"
        to_rotate = ManagedSecret.objects.exclude(ciphertext__startswith=current_prefix).count()
        if options["dry_run"]:
            self.stdout.write(
                f"Managed secret rotation dry-run: total={len(secret_ids)} rotate={to_rotate} "
                f"current_key_id={current_key_id}"
            )
            return

        rotated = 0
        for offset in range(0, len(secret_ids), batch_size):
            batch_ids = secret_ids[offset : offset + batch_size]
            with transaction.atomic():
                rows = list(ManagedSecret.objects.select_for_update().filter(id__in=batch_ids).order_by("id"))
                now = timezone.now()
                changed: list[ManagedSecret] = []
                for secret in rows:
                    if managed_secret_ciphertext_key_id(secret.ciphertext) == current_key_id:
                        continue
                    try:
                        secret.ciphertext = reencrypt_managed_secret(secret.ciphertext)
                    except ManagedSecretError as exc:
                        raise CommandError(f"Failed to rotate managed secret {secret}") from exc
                    metadata = dict(secret.metadata) if isinstance(secret.metadata, dict) else {}
                    metadata["encryption"] = {"version": 2, "key_id": current_key_id}
                    secret.metadata = metadata
                    secret.updated_at = now
                    changed.append(secret)
                if changed:
                    ManagedSecret.objects.bulk_update(changed, ["ciphertext", "metadata", "updated_at"])
                    rotated += len(changed)

        stale = ManagedSecret.objects.exclude(ciphertext__startswith=current_prefix).count()
        broken_after = list_undecryptable_secrets(limit=None)
        if stale or broken_after:
            raise CommandError(
                f"Managed secret rotation verification failed: stale={stale}, undecryptable={len(broken_after)}"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Managed secret rotation complete: total={len(secret_ids)} rotated={rotated} "
                f"current_key_id={current_key_id}"
            )
        )
