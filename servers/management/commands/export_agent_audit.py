"""Verify and export one agent run's immutable audit chain."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from servers.services.agent_audit import iter_agent_audit_export, verify_agent_audit_chain


class Command(BaseCommand):
    help = "Verify and export an agent run audit chain as JSONL."

    def add_arguments(self, parser):
        parser.add_argument("run_ref", type=int)
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        run_ref = options["run_ref"]
        verification = verify_agent_audit_chain(run_ref)
        if not verification["valid"]:
            issue_codes = ", ".join(issue["code"] for issue in verification["issues"][:10])
            raise CommandError(f"Agent audit chain {run_ref} is invalid: {issue_codes}")

        output: Path | None = options["output"]
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("wb") as export_file:
                for chunk in iter_agent_audit_export(run_ref, verification):
                    export_file.write(chunk)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exported {verification['event_count']} events to {output} "
                    f"(final hash {verification['final_event_hash']})"
                )
            )
            return
        for chunk in iter_agent_audit_export(run_ref, verification):
            self.stdout.write(chunk.decode("utf-8"), ending="")
