from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from studio.mcp_tool_runtime import MCPBoundTool

from .skill_registry import SkillDefinition


@dataclass(frozen=True, slots=True)
class CompiledSkillPolicy:
    skill_slug: str
    skill_name: str
    service: str
    applicable_tool_patterns: tuple[re.Pattern[str], ...]
    blocked_tool_patterns: tuple[re.Pattern[str], ...]
    mutating_tool_patterns: tuple[re.Pattern[str], ...]
    required_preflight_tools: tuple[str, ...]
    pinned_arguments: Mapping[str, Any]
    auto_inject_pinned_arguments: bool
    guardrail_summary: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "pinned_arguments", _freeze_json_value(self.pinned_arguments or {}))


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen_dict = {str(key): _freeze_json_value(item) for key, item in value.items()}
        return MappingProxyType(frozen_dict)
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _compile_patterns(raw_patterns: Any, *, skill_slug: str, field_name: str) -> tuple[tuple[re.Pattern[str], ...], list[str]]:
    if not raw_patterns:
        return (), []

    if not isinstance(raw_patterns, Sequence) or isinstance(raw_patterns, (str, bytes, bytearray)):
        return (), [f"{skill_slug}: {field_name} must be a JSON array of regex strings"]

    compiled: list[re.Pattern[str]] = []
    errors: list[str] = []
    for raw in raw_patterns:
        pattern = str(raw or "").strip()
        if not pattern:
            continue
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            errors.append(f"{skill_slug}: invalid regex in {field_name}: {pattern!r} ({exc})")
    return tuple(compiled), errors


def compile_skill_policies(skills: list[SkillDefinition]) -> tuple[list[CompiledSkillPolicy], list[str]]:
    policies: list[CompiledSkillPolicy] = []
    errors: list[str] = []

    for skill in skills:
        policy = skill.runtime_policy if isinstance(skill.runtime_policy, Mapping) else {}
        if not policy:
            continue

        applicable_patterns, applicable_errors = _compile_patterns(
            policy.get("applicable_tool_patterns") or policy.get("tool_name_patterns"),
            skill_slug=skill.slug,
            field_name="applicable_tool_patterns",
        )
        blocked_patterns, blocked_errors = _compile_patterns(
            policy.get("blocked_tool_patterns"),
            skill_slug=skill.slug,
            field_name="blocked_tool_patterns",
        )
        mutating_patterns, mutating_errors = _compile_patterns(
            policy.get("mutating_tool_patterns"),
            skill_slug=skill.slug,
            field_name="mutating_tool_patterns",
        )
        errors.extend(applicable_errors)
        errors.extend(blocked_errors)
        errors.extend(mutating_errors)

        raw_required = policy.get("required_preflight_tools") or []
        if raw_required and (
            not isinstance(raw_required, Sequence) or isinstance(raw_required, (str, bytes, bytearray))
        ):
            errors.append(f"{skill.slug}: required_preflight_tools must be a JSON array of tool names")
            required_preflight_tools: tuple[str, ...] = ()
        else:
            required_preflight_tools = tuple(str(item).strip() for item in raw_required if str(item).strip())

        raw_pinned_arguments = policy.get("pinned_arguments") or {}
        if raw_pinned_arguments and not isinstance(raw_pinned_arguments, Mapping):
            errors.append(f"{skill.slug}: pinned_arguments must be a JSON object")
            pinned_arguments: dict[str, Any] = {}
        else:
            pinned_arguments = dict(raw_pinned_arguments)

        policies.append(
            CompiledSkillPolicy(
                skill_slug=skill.slug,
                skill_name=skill.name,
                service=skill.service,
                applicable_tool_patterns=applicable_patterns,
                blocked_tool_patterns=blocked_patterns,
                mutating_tool_patterns=mutating_patterns,
                required_preflight_tools=required_preflight_tools,
                pinned_arguments=pinned_arguments,
                auto_inject_pinned_arguments=bool(policy.get("auto_inject_pinned_arguments", True)),
                guardrail_summary=skill.guardrail_summary,
            )
        )

    pinned_index: dict[tuple[str, str], dict[str, list[str]]] = {}
    for policy in policies:
        service_key = policy.service or policy.skill_slug
        for arg_name, value in policy.pinned_arguments.items():
            arg_key = (service_key, arg_name)
            pinned_index.setdefault(arg_key, {}).setdefault(repr(value), []).append(policy.skill_name)

    for (service_key, arg_name), value_map in pinned_index.items():
        if len(value_map) <= 1:
            continue
        rendered = ", ".join(
            f"{value} via {', '.join(skill_names)}" for value, skill_names in sorted(value_map.items())
        )
        errors.append(
            f"Conflicting pinned arguments for service '{service_key}', argument '{arg_name}': {rendered}"
        )

    return policies, errors


def _matches_any(patterns: tuple[re.Pattern[str], ...], value: str) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def apply_skill_policies(
    policies: list[CompiledSkillPolicy],
    binding: MCPBoundTool,
    args: dict[str, Any],
    executed_mcp_tools: set[str],
) -> tuple[dict[str, Any], list[str], str | None]:
    current_args = dict(args or {})
    messages: list[str] = []
    tool_name = binding.tool_name

    for policy in policies:
        if policy.blocked_tool_patterns and _matches_any(policy.blocked_tool_patterns, tool_name):
            return current_args, messages, (
                f"Blocked by skill '{policy.skill_name}': MCP tool '{tool_name}' is forbidden by corporate guardrails."
            )

        applies = not policy.applicable_tool_patterns or _matches_any(policy.applicable_tool_patterns, tool_name)
        if not applies:
            continue

        if policy.mutating_tool_patterns and _matches_any(policy.mutating_tool_patterns, tool_name):
            missing_preflight = [name for name in policy.required_preflight_tools if name not in executed_mcp_tools]
            if missing_preflight:
                return current_args, messages, (
                    f"Blocked by skill '{policy.skill_name}': run the required preflight MCP tools first: "
                    f"{', '.join(missing_preflight)}."
                )

        injected_items: list[str] = []
        for arg_name, expected_value in policy.pinned_arguments.items():
            current_value = current_args.get(arg_name)
            if current_value in (None, ""):
                if not policy.auto_inject_pinned_arguments:
                    return current_args, messages, (
                        f"Blocked by skill '{policy.skill_name}': argument '{arg_name}' must be set to "
                        f"{expected_value!r}."
                    )
                current_args[arg_name] = expected_value
                injected_items.append(f"{arg_name}={expected_value!r}")
                continue

            if current_value != expected_value:
                return current_args, messages, (
                    f"Blocked by skill '{policy.skill_name}': argument '{arg_name}' must be "
                    f"{expected_value!r}, got {current_value!r}."
                )

        if injected_items:
            messages.append(
                f"Skill guardrail '{policy.skill_name}' applied pinned arguments: {', '.join(injected_items)}."
            )

    return current_args, messages, None
