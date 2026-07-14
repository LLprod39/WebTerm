"""Optionally raise stored ServerAgent budgets that still use legacy defaults.

Does not force every row — only agents still on the pre-complex defaults
(max_iterations=20 and/or session_timeout_seconds=600) when those match the
old product defaults. Dry-run by default.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from servers.agent_budgets import (
    FULL_DEFAULT_MAX_ITERATIONS,
    FULL_DEFAULT_SESSION_TIMEOUT_SEC,
)
from servers.models import ServerAgent

LEGACY_ITERATIONS = 20
LEGACY_TIMEOUT = 600


class Command(BaseCommand):
    help = (
        "Bump ServerAgent rows still on legacy budget defaults (20 iter / 600s) "
        f"to complex-task defaults ({FULL_DEFAULT_MAX_ITERATIONS} / {FULL_DEFAULT_SESSION_TIMEOUT_SEC}). "
        "Dry-run unless --apply is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist updates (default is dry-run).",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Limit to a single user id.",
        )

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))
        user_id = options.get("user_id")
        qs = ServerAgent.objects.all()
        if user_id is not None:
            qs = qs.filter(user_id=user_id)

        targets = qs.filter(max_iterations=LEGACY_ITERATIONS) | qs.filter(
            session_timeout_seconds=LEGACY_TIMEOUT
        )
        targets = targets.distinct().order_by("id")
        count = targets.count()
        self.stdout.write(f"Candidates: {count}")
        updated = 0
        for agent in targets.iterator():
            changed = []
            if agent.max_iterations == LEGACY_ITERATIONS:
                agent.max_iterations = FULL_DEFAULT_MAX_ITERATIONS
                changed.append(f"max_iterations {LEGACY_ITERATIONS}->{FULL_DEFAULT_MAX_ITERATIONS}")
            if agent.session_timeout_seconds == LEGACY_TIMEOUT:
                agent.session_timeout_seconds = FULL_DEFAULT_SESSION_TIMEOUT_SEC
                changed.append(
                    f"session_timeout {LEGACY_TIMEOUT}->{FULL_DEFAULT_SESSION_TIMEOUT_SEC}"
                )
            if not changed:
                continue
            updated += 1
            self.stdout.write(f"  agent id={agent.id} name={agent.name!r}: {', '.join(changed)}")
            if apply:
                agent.save(update_fields=["max_iterations", "session_timeout_seconds"])

        if apply:
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} agent(s)."))
        else:
            self.stdout.write(
                self.style.WARNING(f"Dry-run: would update {updated} agent(s). Pass --apply to save.")
            )
