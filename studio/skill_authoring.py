from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings

from servers.services.tool_catalog import list_agent_tool_names

from .skill_policy import compile_skill_policies
from .skill_registry import _load_skill_from_dir, _split_frontmatter

SKILL_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")
RECOMMENDED_SECTION_TITLES = (
    "## When to use",
    "## Mandatory workflow",
    "## Hard rules",
    "## Reporting",
)
KNOWN_SAFETY_LEVELS = {"low", "standard", "medium", "high", "critical"}
KNOWN_AGENT_TOOLS = set(list_agent_tool_names())


@dataclass(slots=True)
class SkillValidationResult:
    slug: str
    path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "path": self.path,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "is_valid": self.is_valid,
        }


def skill_root_for_writes() -> Path:
    configured = getattr(settings, "STUDIO_SKILLS_DIRS", None)
    if configured:
        for item in configured:
            value = str(item or "").strip()
            if value:
                return Path(value).expanduser()
    return Path(getattr(settings, "BASE_DIR", ".")) / "studio" / "skills"


def existing_skill_roots() -> list[Path]:
    configured = getattr(settings, "STUDIO_SKILLS_DIRS", None)
    if configured:
        roots = [Path(item).expanduser() for item in configured if str(item).strip()]
    else:
        roots = [Path(getattr(settings, "BASE_DIR", ".")) / "studio" / "skills"]
    return [root for root in roots if root.exists() and root.is_dir()]


def slugify_skill_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if len(text) > 64:
        text = text[:64].rstrip("-")
    if not SKILL_SLUG_RE.fullmatch(text):
        raise ValueError(
            "Skill slug must use lowercase letters, digits, and hyphens only, up to 64 characters."
        )
    return text


def parse_csv_items(raw_value: str | list[Any] | tuple[Any, ...] | None) -> list[str]:
    if not raw_value:
        return []
    result: list[str] = []
    seen: set[str] = set()
    parts = [str(item) for item in raw_value] if isinstance(raw_value, (list, tuple)) else str(raw_value).split(",")
    for part in parts:
        item = part.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def parse_key_value_pairs(raw_values: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in raw_values or []:
        item = str(raw or "").strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Pinned argument '{item}' must use key=value format.")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Pinned argument '{item}' must have a non-empty key.")
        result[key] = value
    return result


def build_runtime_policy(
    *,
    applicable_tool_patterns: list[str] | None = None,
    blocked_tool_patterns: list[str] | None = None,
    mutating_tool_patterns: list[str] | None = None,
    required_preflight_tools: list[str] | None = None,
    pinned_arguments: dict[str, Any] | None = None,
    auto_inject_pinned_arguments: bool = True,
) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    if applicable_tool_patterns:
        policy["applicable_tool_patterns"] = list(applicable_tool_patterns)
    if blocked_tool_patterns:
        policy["blocked_tool_patterns"] = list(blocked_tool_patterns)
    if mutating_tool_patterns:
        policy["mutating_tool_patterns"] = list(mutating_tool_patterns)
    if required_preflight_tools:
        policy["required_preflight_tools"] = list(required_preflight_tools)
    if pinned_arguments:
        policy["pinned_arguments"] = dict(pinned_arguments)
    if policy:
        policy["auto_inject_pinned_arguments"] = bool(auto_inject_pinned_arguments)
    return policy


def _render_frontmatter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def render_skill_markdown(
    *,
    name: str,
    description: str,
    service: str = "",
    category: str = "",
    safety_level: str = "standard",
    ui_hint: str = "",
    tags: list[str] | None = None,
    guardrail_summary: list[str] | None = None,
    recommended_tools: list[str] | None = None,
    runtime_policy: dict[str, Any] | None = None,
) -> str:
    metadata_items = [
        ("name", name.strip()),
        ("description", description.strip()),
        ("service", service.strip()),
        ("category", category.strip()),
        ("safety_level", safety_level.strip() or "standard"),
        ("ui_hint", ui_hint.strip()),
        ("guardrail_summary", list(guardrail_summary or [])),
        ("recommended_tools", list(recommended_tools or [])),
        ("runtime_policy", dict(runtime_policy or {})),
        ("tags", list(tags or [])),
    ]

    frontmatter_lines = ["---"]
    for key, value in metadata_items:
        if value in ("", [], {}):
            continue
        frontmatter_lines.append(f"{key}: {_render_frontmatter_value(value)}")
    frontmatter_lines.append("---")

    service_label = service.strip() or "the target service"
    mcp_example = f"{service.strip()}_" if service.strip() else "service_"
    runtime_note = (
        "If this skill defines runtime policy, treat it as mandatory and assume those guardrails are enforced by the platform."
    )

    body = f"""# {name}

Use this skill for work done through MCP tools against {service_label}.

## When to use

- The user asks for operational work that touches {service_label}.
- The request is free-form, ambiguous, or safety-sensitive.
- The environment, tenant, realm, project, or profile must be resolved before mutation.

## Mandatory workflow

1. Start with environment and permission discovery using the correct read-only MCP tools.
2. Normalize the user request into a short structured plan before making changes.
3. Resolve exact targets with read-only discovery tools before any mutation.
4. Execute only the minimum required mutations.
5. Run read-only verification after every mutation and compare the final state with the request.
6. Stop and ask the user whenever discovery is incomplete or the target is ambiguous.

## Hard rules

- Always prefer exact identifiers over fuzzy matching.
- Never mutate if discovery data is incomplete.
- Never switch context mid-run unless the user explicitly asks and confirms it.
- Always pass required environment arguments explicitly when the MCP tool supports them.
- {runtime_note}
- If this skill works with service-specific MCP tools, use the original tool names in the policy, for example `{mcp_example}current_environment`.

## Reporting

- State which environment, tenant, realm, profile, or project was used.
- State which entities were discovered before mutation.
- State which mutations were applied and which were skipped.
- State which verification calls were used.
- State any ambiguity, blockers, or follow-up required.
"""

    return "\n".join(frontmatter_lines) + "\n" + body.strip() + "\n"


def scaffold_skill(
    *,
    name: str,
    description: str,
    slug: str | None = None,
    service: str = "",
    category: str = "",
    safety_level: str = "standard",
    ui_hint: str = "",
    tags: list[str] | None = None,
    guardrail_summary: list[str] | None = None,
    recommended_tools: list[str] | None = None,
    runtime_policy: dict[str, Any] | None = None,
    with_scripts: bool = False,
    with_references: bool = False,
    with_assets: bool = False,
    force: bool = False,
) -> Path:
    resolved_slug = slugify_skill_name(slug or name)
    root = skill_root_for_writes()
    skill_dir = root / resolved_slug
    skill_file = skill_dir / "SKILL.md"

    if skill_dir.exists() and not force:
        raise FileExistsError(f"Skill directory already exists: {skill_dir}")

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(
        render_skill_markdown(
            name=name,
            description=description,
            service=service,
            category=category,
            safety_level=safety_level,
            ui_hint=ui_hint,
            tags=tags,
            guardrail_summary=guardrail_summary,
            recommended_tools=recommended_tools,
            runtime_policy=runtime_policy,
        ),
        encoding="utf-8",
    )

    if with_scripts:
        (skill_dir / "scripts").mkdir(exist_ok=True)
    if with_references:
        (skill_dir / "references").mkdir(exist_ok=True)
    if with_assets:
        (skill_dir / "assets").mkdir(exist_ok=True)

    return skill_dir


def validate_skill_dir(skill_dir: Path) -> SkillValidationResult:
    skill_dir = Path(skill_dir)
    result = SkillValidationResult(slug=skill_dir.name, path=str(skill_dir))
    skill_file = skill_dir / "SKILL.md"

    if not SKILL_SLUG_RE.fullmatch(skill_dir.name):
        result.errors.append(
            "Directory name must use lowercase letters, digits, and hyphens only, up to 64 characters."
        )

    if not skill_file.exists():
        result.errors.append("Missing SKILL.md")
        return result

    raw_content = skill_file.read_text(encoding="utf-8")
    if not raw_content.startswith("---"):
        result.errors.append("SKILL.md must start with a frontmatter block delimited by ---")
        return result

    metadata, body = _split_frontmatter(raw_content)
    if not metadata:
        result.errors.append("Frontmatter is missing or could not be parsed")

    name = str(metadata.get("name") or "").strip()
    description = str(metadata.get("description") or "").strip()
    if not name:
        result.errors.append("Frontmatter field 'name' is required")
    if not description:
        result.errors.append("Frontmatter field 'description' is required")
    elif len(description) < 20:
        result.warnings.append("Description is very short; make trigger conditions more explicit")

    safety_level = str(metadata.get("safety_level") or "").strip().lower()
    if safety_level and safety_level not in KNOWN_SAFETY_LEVELS:
        result.warnings.append(
            f"Unknown safety_level '{metadata.get('safety_level')}'. Expected one of: {', '.join(sorted(KNOWN_SAFETY_LEVELS))}."
        )

    runtime_policy = metadata.get("runtime_policy")
    if "runtime_policy" in metadata and runtime_policy and not isinstance(runtime_policy, dict):
        result.errors.append("Frontmatter field 'runtime_policy' must be a JSON object")

    if not body.strip():
        result.errors.append("Skill body is empty")
    else:
        if not body.lstrip().startswith("# "):
            result.warnings.append("Skill body should start with a level-1 title")
        body_line_count = len(body.splitlines())
        if body_line_count > 500:
            result.warnings.append("Skill body is longer than 500 lines; move details into references/")
        for section_title in RECOMMENDED_SECTION_TITLES:
            if section_title not in body:
                result.warnings.append(f"Recommended section missing: {section_title}")

    skill = _load_skill_from_dir(skill_dir)
    if skill is None:
        result.errors.append("Skill could not be loaded from SKILL.md")
        return result

    unknown_tools = [tool_name for tool_name in skill.recommended_tools if tool_name not in KNOWN_AGENT_TOOLS]
    if unknown_tools:
        rendered = ", ".join(sorted(unknown_tools))
        result.warnings.append(f"recommended_tools contains unknown agent tools: {rendered}")

    if not skill.tags:
        result.warnings.append("Add tags so admins can find this skill in the catalog")
    if not skill.service:
        result.warnings.append("Set 'service' so admins can filter the skill catalog")
    if skill.safety_level.lower() in {"high", "critical"} and not skill.runtime_policy:
        result.warnings.append("High-safety skills should define runtime_policy guardrails")
    if skill.guardrail_summary == () and skill.runtime_policy:
        result.warnings.append("runtime_policy is present but guardrail_summary is empty")

    compiled_policies, policy_errors = compile_skill_policies([skill])
    result.errors.extend(policy_errors)

    if compiled_policies:
        policy = compiled_policies[0]
        if policy.required_preflight_tools and not policy.mutating_tool_patterns:
            result.warnings.append(
                "required_preflight_tools is set but mutating_tool_patterns is empty; the preflight may never be enforced"
            )

    return result


def validate_skills(slugs: list[str] | None = None) -> list[SkillValidationResult]:
    selected = {str(item).strip().lower() for item in (slugs or []) if str(item).strip()}
    results: list[SkillValidationResult] = []
    seen: dict[str, Path] = {}

    for root in existing_skill_roots():
        for skill_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name.lower()):
            if selected and skill_dir.name.lower() not in selected:
                continue
            results.append(validate_skill_dir(skill_dir))
            if skill_dir.name.lower() in seen:
                results[-1].warnings.append(f"Duplicate slug also exists at {seen[skill_dir.name.lower()]}")
            else:
                seen[skill_dir.name.lower()] = skill_dir

    return results
