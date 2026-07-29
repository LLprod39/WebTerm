from __future__ import annotations

import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core_ui.access import PROFILE_STAFF_FLAGS, VALID_ACCESS_PROFILES, access_profile_permissions
from core_ui.models import UserAppPermission


class Command(BaseCommand):
    help = "Create or update a platform administrator while reading the password from stdin."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument("--profile", default="admin_full")
        parser.add_argument("--password-stdin", action="store_true", required=True)

    def handle(self, *args, **options):
        profile = str(options["profile"] or "").strip()
        if profile not in VALID_ACCESS_PROFILES or profile in {"custom", "reset_defaults", "server_only"}:
            raise CommandError("profile must be an assignable access profile")

        password = sys.stdin.readline()
        if not password:
            raise CommandError("administrator password is required on stdin")
        password = password.removesuffix("\n").removesuffix("\r")
        if not password or sys.stdin.read(1):
            raise CommandError("administrator password stdin must contain exactly one non-empty line")

        username = str(options["username"] or "").strip()
        email = str(options["email"] or "").strip()
        if not username:
            raise CommandError("username is required")

        User = get_user_model()
        target = access_profile_permissions(profile)
        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "is_staff": True,
                    "is_superuser": True,
                    "is_active": True,
                },
            )
            user.email = email or user.email
            user.is_staff = PROFILE_STAFF_FLAGS.get(profile, True)
            user.is_superuser = True
            user.is_active = True
            user.set_password(password)
            user.save()
            for feature, allowed in target.items():
                UserAppPermission.objects.update_or_create(
                    user=user,
                    feature=feature,
                    defaults={"allowed": bool(allowed)},
                )

        state = "Created" if created else "Updated"
        self.stdout.write(f"{state} administrator: {username}")
        self.stdout.write(f"Applied access profile '{profile}' ({len(target)} features)")
