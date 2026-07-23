from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from studio.skill_authoring import existing_skill_roots, validate_skills


class Command(BaseCommand):
    help = "Validate Studio skill packs and report structural or policy issues."

    def add_arguments(self, parser):
        parser.add_argument(
            "slugs",
            nargs="*",
            help="Optional skill slugs to validate. Defaults to all skills in the configured roots.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail the command on warnings as well as errors.",
        )

    def handle(self, *args, **options):
        slugs = [str(item).strip() for item in options.get("slugs") or [] if str(item).strip()]
        if not existing_skill_roots():
            raise CommandError("No Studio skill roots exist yet.")

        results = validate_skills(slugs or None)
        if slugs and not results:
            raise CommandError(f"No skills matched: {', '.join(slugs)}")

        available_slugs = {result.slug.lower() for result in results}
        missing = [slug for slug in slugs if slug.lower() not in available_slugs]
        if missing:
            raise CommandError(f"Skills not found: {', '.join(missing)}")

        error_count = 0
        warning_count = 0
        for result in results:
            if result.errors:
                status = self.style.ERROR("ERROR")
            elif result.warnings:
                status = self.style.WARNING("WARN")
            else:
                status = self.style.SUCCESS("OK")

            self.stdout.write(f"[{status}] {result.slug} :: {result.path}")
            for item in result.errors:
                error_count += 1
                self.stdout.write(f"  error: {item}")
            for item in result.warnings:
                warning_count += 1
                self.stdout.write(f"  warning: {item}")

        self.stdout.write("")
        self.stdout.write(f"Validated {len(results)} skill(s): {error_count} error(s), {warning_count} warning(s)")

        if error_count:
            raise CommandError("Skill validation failed.")
        if warning_count and options.get("strict"):
            raise CommandError("Skill validation failed in strict mode due to warnings.")
