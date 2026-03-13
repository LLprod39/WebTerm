from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from django.conf import settings

_FRONTMATTER_BOUNDARY = "---"
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
try:
    import yaml
except Exception:  # pragma: no cover - optional dependency in minimal envs
    yaml = None


class SkillNotFoundError(KeyError):
    """Raised when a requested skill slug cannot be resolved."""


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    slug: str
    name: str
    description: str
    path: str
    tags: tuple[str, ...]
    service: str
    category: str
    safety_level: str
    ui_hint: str
    guardrail_summary: tuple[str, ...]
    recommended_tools: tuple[str, ...]
    runtime_policy: Mapping[str, Any]
    metadata: Mapping[str, Any]
    content: str

    def __post_init__(self):
        object.__setattr__(self, "runtime_policy", _freeze_json_value(self.runtime_policy or {}))
        object.__setattr__(self, "metadata", _freeze_json_value(self.metadata or {}))

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "service": self.service,
            "category": self.category,
            "safety_level": self.safety_level,
            "ui_hint": self.ui_hint,
            "guardrail_summary": list(self.guardrail_summary),
            "recommended_tools": list(self.recommended_tools),
            "runtime_enforced": bool(self.runtime_policy),
        }

    def to_detail_dict(self) -> dict[str, Any]:
        data = self.to_summary_dict()
        data["runtime_policy"] = _json_compatible_value(self.runtime_policy)
        data["metadata"] = _json_compatible_value(self.metadata)
        data["content"] = self.content
        return data


def _skill_roots() -> list[Path]:
    configured = getattr(settings, "STUDIO_SKILLS_DIRS", None)
    if configured:
        roots = [Path(item).expanduser() for item in configured if str(item).strip()]
    else:
        roots = [Path(getattr(settings, "BASE_DIR", ".")) / "studio" / "skills"]
    return [root for root in roots if root.exists() and root.is_dir()]


def _clean_scalar(value: str) -> str:
    return value.strip().strip("\"'")


def _parse_frontmatter_value(key: str, value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""

    if raw[0] in "[{":
        with_context = raw
        try:
            return json.loads(with_context)
        except json.JSONDecodeError:
            pass

    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_clean_scalar(item) for item in inner.split(",") if item.strip()]

    if key in {"tags", "guardrail_summary", "recommended_tools"}:
        return [_clean_scalar(item) for item in raw.split(",") if item.strip()]

    return _clean_scalar(raw)


def _parse_frontmatter_lines(lines: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        metadata[key.strip()] = _parse_frontmatter_value(key.strip(), raw_value)
    return metadata


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith(_FRONTMATTER_BOUNDARY):
        return {}, content

    lines = content.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_BOUNDARY:
        return {}, content

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONTMATTER_BOUNDARY:
            end_index = index
            break

    if end_index is None:
        return {}, content

    frontmatter_lines = lines[1:end_index]
    metadata = _parse_frontmatter_lines(frontmatter_lines)
    if yaml is not None:
        try:
            parsed_yaml = yaml.safe_load("\n".join(frontmatter_lines))
            if isinstance(parsed_yaml, dict):
                metadata = parsed_yaml
        except Exception:
            pass

    body = "\n".join(lines[end_index + 1 :]).lstrip()
    return metadata, body


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen_dict = {str(key): _freeze_json_value(item) for key, item in value.items()}
        return MappingProxyType(frozen_dict)
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _json_compatible_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_compatible_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_compatible_value(item) for item in value]
    return value


def _extract_title(body: str, fallback: str) -> str:
    match = _TITLE_RE.search(body)
    if match:
        return match.group(1).strip()
    return fallback.replace("-", " ").replace("_", " ").strip().title() or fallback


def _extract_description(body: str) -> str:
    paragraphs = re.split(r"\n\s*\n", body)
    for paragraph in paragraphs:
        text = paragraph.strip()
        if not text or text.startswith("#"):
            continue
        compact = re.sub(r"\s+", " ", text)
        return compact[:280]
    return ""


def _load_skill_from_dir(skill_dir: Path) -> SkillDefinition | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    raw_content = skill_file.read_text(encoding="utf-8")
    metadata, body = _split_frontmatter(raw_content)
    slug = skill_dir.name
    name = str(metadata.get("name") or _extract_title(body, slug)).strip() or slug
    description = str(metadata.get("description") or _extract_description(body)).strip()
    tags_value = metadata.get("tags") or []
    if isinstance(tags_value, str):
        tags = tuple(item for item in (_clean_scalar(part) for part in tags_value.split(",")) if item)
    elif isinstance(tags_value, list):
        tags = tuple(str(item).strip() for item in tags_value if str(item).strip())
    else:
        tags = ()

    guardrails_value = metadata.get("guardrail_summary") or []
    if isinstance(guardrails_value, str):
        guardrail_summary = tuple(item for item in (_clean_scalar(part) for part in guardrails_value.split(",")) if item)
    elif isinstance(guardrails_value, list):
        guardrail_summary = tuple(str(item).strip() for item in guardrails_value if str(item).strip())
    else:
        guardrail_summary = ()

    recommended_tools_value = metadata.get("recommended_tools") or []
    if isinstance(recommended_tools_value, str):
        recommended_tools = tuple(
            item for item in (_clean_scalar(part) for part in recommended_tools_value.split(",")) if item
        )
    elif isinstance(recommended_tools_value, list):
        recommended_tools = tuple(str(item).strip() for item in recommended_tools_value if str(item).strip())
    else:
        recommended_tools = ()

    runtime_policy = metadata.get("runtime_policy") if isinstance(metadata.get("runtime_policy"), dict) else {}

    return SkillDefinition(
        slug=slug,
        name=name,
        description=description,
        path=os.fspath(skill_file.resolve()),
        tags=tags,
        service=str(metadata.get("service") or "").strip(),
        category=str(metadata.get("category") or "").strip(),
        safety_level=str(metadata.get("safety_level") or "").strip(),
        ui_hint=str(metadata.get("ui_hint") or "").strip(),
        guardrail_summary=guardrail_summary,
        recommended_tools=recommended_tools,
        runtime_policy=runtime_policy,
        metadata=metadata,
        content=body,
    )


def list_skills() -> list[SkillDefinition]:
    discovered: dict[str, SkillDefinition] = {}

    for root in _skill_roots():
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            skill = _load_skill_from_dir(child)
            if skill is None or skill.slug in discovered:
                continue
            discovered[skill.slug] = skill

    return sorted(discovered.values(), key=lambda item: item.name.lower())


def get_skill(slug_or_name: str) -> SkillDefinition:
    needle = str(slug_or_name or "").strip().lower()
    if not needle:
        raise SkillNotFoundError("Skill slug is required")

    for skill in list_skills():
        if skill.slug.lower() == needle or skill.name.lower() == needle:
            return skill

    raise SkillNotFoundError(f"Skill not found: {slug_or_name}")


def normalise_skill_slugs(raw_values: Any) -> list[str]:
    if not isinstance(raw_values, list):
        return []

    result: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        value = item.get("slug") or item.get("name") if isinstance(item, dict) else item
        slug = str(value or "").strip()
        if not slug:
            continue
        key = slug.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(slug)
    return result


def resolve_skills(skill_slugs: list[str]) -> tuple[list[SkillDefinition], list[str]]:
    if not skill_slugs:
        return [], []

    catalog = list_skills()
    by_slug = {skill.slug.lower(): skill for skill in catalog}
    by_name = {skill.name.lower(): skill for skill in catalog}

    resolved: list[SkillDefinition] = []
    errors: list[str] = []
    seen: set[str] = set()
    for raw_slug in skill_slugs:
        needle = str(raw_slug or "").strip().lower()
        if not needle:
            continue
        skill = by_slug.get(needle) or by_name.get(needle)
        if skill is None:
            errors.append(f"{raw_slug}: not found")
            continue
        if skill.slug in seen:
            continue
        seen.add(skill.slug)
        resolved.append(skill)
    return resolved, errors


def build_skill_catalog_description(skills: list[SkillDefinition]) -> str:
    if not skills:
        return ""

    sections = ["### Attached skills"]
    for skill in skills:
        tags = f"Tags: {', '.join(skill.tags)}" if skill.tags else "Tags: none"
        guardrails = (
            "Runtime guardrails: " + "; ".join(skill.guardrail_summary)
            if skill.guardrail_summary
            else "Runtime guardrails: none"
        )
        safety = f"Safety level: {skill.safety_level}" if skill.safety_level else "Safety level: standard"
        service = f"Service: {skill.service}" if skill.service else "Service: generic"
        sections.append(
            "\n".join(
                [
                    f"### {skill.slug}",
                    f"Name: {skill.name}",
                    f"Description: {skill.description or 'No description provided.'}",
                    service,
                    tags,
                    safety,
                    guardrails,
                    "Use read_skill to open the full instructions when needed.",
                ]
            )
        )
    return "\n\n".join(sections)
