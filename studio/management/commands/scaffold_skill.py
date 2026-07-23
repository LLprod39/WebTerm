from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from studio.skill_authoring import (
    build_runtime_policy,
    parse_csv_items,
    parse_key_value_pairs,
    scaffold_skill,
    slugify_skill_name,
    validate_skill_dir,
)
from studio.skill_templates import get_skill_template, list_skill_templates


class Command(BaseCommand):
    help = "Create a new Studio skill pack using the corporate scaffold."

    @staticmethod
    def _normalise_multi_value(raw_value) -> list[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        value = str(raw_value).strip()
        return [value] if value else []

    def add_arguments(self, parser):
        parser.add_argument("name", type=str, help="Display name for the skill.")
        parser.add_argument(
            "--template",
            type=str,
            default="",
            help="Optional skill template slug. Available: " + ", ".join(item.slug for item in list_skill_templates()),
        )
        parser.add_argument(
            "--description",
            type=str,
            default="",
            help="Trigger description: when the skill should be attached and used.",
        )
        parser.add_argument("--slug", type=str, default="", help="Optional folder slug. Defaults to a slugified name.")
        parser.add_argument("--service", type=str, default="", help="Service name for catalog grouping, e.g. keycloak.")
        parser.add_argument("--category", type=str, default="", help="Catalog category, e.g. Identity and Access.")
        parser.add_argument(
            "--safety-level", type=str, default="standard", help="low | standard | medium | high | critical"
        )
        parser.add_argument(
            "--ui-hint", type=str, default="", help="Short admin-facing hint shown in the Studio catalog."
        )
        parser.add_argument("--tags", type=str, default="", help="Comma-separated tags.")
        parser.add_argument(
            "--recommended-tools", type=str, default="", help="Comma-separated recommended agent tools."
        )
        parser.add_argument(
            "--guardrail-summary", type=str, default="", help="Comma-separated guardrail summary bullets."
        )
        parser.add_argument(
            "--runtime-policy",
            type=str,
            default="",
            help="Raw JSON object for runtime_policy. If provided, it is merged with the pattern/key-value flags below.",
        )
        parser.add_argument(
            "--applicable-tool-pattern",
            action="append",
            default=[],
            help="Regex for original MCP tool names this skill policy applies to. Repeat for multiple values.",
        )
        parser.add_argument(
            "--blocked-tool-pattern",
            action="append",
            default=[],
            help="Regex for original MCP tool names blocked by the skill. Repeat for multiple values.",
        )
        parser.add_argument(
            "--mutating-tool-pattern",
            action="append",
            default=[],
            help="Regex for original MCP tool names considered mutating. Repeat for multiple values.",
        )
        parser.add_argument(
            "--required-preflight-tool",
            action="append",
            default=[],
            help="Original MCP tool name that must run before mutations. Repeat for multiple values.",
        )
        parser.add_argument(
            "--pinned-argument",
            action="append",
            default=[],
            help="Pinned MCP argument in key=value format. Repeat for multiple values.",
        )
        parser.add_argument(
            "--no-auto-inject-pinned-arguments",
            action="store_true",
            help="Do not auto-inject pinned arguments; instead block if they are missing.",
        )
        parser.add_argument("--with-scripts", action="store_true", help="Create a scripts/ directory.")
        parser.add_argument("--with-references", action="store_true", help="Create a references/ directory.")
        parser.add_argument("--with-assets", action="store_true", help="Create an assets/ directory.")
        parser.add_argument("--force", action="store_true", help="Overwrite an existing skill directory.")

    def handle(self, *args, **options):
        name = str(options["name"]).strip()
        template_slug = str(options.get("template") or "").strip()
        template = get_skill_template(template_slug) if template_slug else None
        if template_slug and template is None:
            raise CommandError(f"Unknown template: {template_slug}")

        defaults = dict(template.defaults) if template else {}
        description = str(options["description"]).strip() or str(defaults.get("description") or "").strip()
        if not name:
            raise CommandError("name is required")
        if not description:
            raise CommandError("description is required")

        slug = str(options.get("slug") or "").strip() or slugify_skill_name(name)

        raw_runtime_policy = str(options.get("runtime_policy") or "").strip()
        runtime_policy: dict[str, object] = dict(defaults.get("runtime_policy") or {})
        if raw_runtime_policy:
            try:
                parsed_policy = json.loads(raw_runtime_policy)
            except json.JSONDecodeError as exc:
                raise CommandError(f"--runtime-policy must be valid JSON: {exc}") from exc
            if not isinstance(parsed_policy, dict):
                raise CommandError("--runtime-policy must be a JSON object")
            runtime_policy.update(parsed_policy)

        generated_policy = build_runtime_policy(
            applicable_tool_patterns=self._normalise_multi_value(options.get("applicable_tool_pattern")),
            blocked_tool_patterns=self._normalise_multi_value(options.get("blocked_tool_pattern")),
            mutating_tool_patterns=self._normalise_multi_value(options.get("mutating_tool_pattern")),
            required_preflight_tools=self._normalise_multi_value(options.get("required_preflight_tool")),
            pinned_arguments=parse_key_value_pairs(self._normalise_multi_value(options.get("pinned_argument"))),
            auto_inject_pinned_arguments=not bool(options.get("no_auto_inject_pinned_arguments")),
        )
        runtime_policy.update(generated_policy)

        skill_dir = scaffold_skill(
            name=name,
            description=description,
            slug=slug,
            service=str(options.get("service") or defaults.get("service") or "").strip(),
            category=str(options.get("category") or defaults.get("category") or "").strip(),
            safety_level=str(options.get("safety_level") or defaults.get("safety_level") or "standard").strip()
            or "standard",
            ui_hint=str(options.get("ui_hint") or defaults.get("ui_hint") or "").strip(),
            tags=parse_csv_items(options.get("tags") or defaults.get("tags")),
            guardrail_summary=parse_csv_items(options.get("guardrail_summary") or defaults.get("guardrail_summary")),
            recommended_tools=parse_csv_items(options.get("recommended_tools") or defaults.get("recommended_tools")),
            runtime_policy=runtime_policy,
            with_scripts=bool(options.get("with_scripts")),
            with_references=bool(options.get("with_references")),
            with_assets=bool(options.get("with_assets")),
            force=bool(options.get("force")),
        )

        validation = validate_skill_dir(skill_dir)

        self.stdout.write(self.style.SUCCESS(f"Created skill scaffold: {skill_dir}"))
        self.stdout.write(f"Slug: {slug}")
        self.stdout.write(f"SKILL.md: {skill_dir / 'SKILL.md'}")
        if validation.warnings:
            self.stdout.write(self.style.WARNING("Validation warnings:"))
            for item in validation.warnings:
                self.stdout.write(f"  - {item}")
        if validation.errors:
            self.stdout.write(self.style.ERROR("Validation errors:"))
            for item in validation.errors:
                self.stdout.write(f"  - {item}")
            raise CommandError("Skill scaffold was created but did not pass validation.")

        self.stdout.write(self.style.SUCCESS("Skill scaffold passes validation."))
